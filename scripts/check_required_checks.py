# SPDX-License-Identifier: MIT
"""Compare each repository's workflow jobs against its required status checks.

Adding a workflow to a repository does not add it to the ruleset, so a suite can
run on every pull request and gate nothing (kindspec/.github#3). This fails when:

  UNGATED      a job that runs on pull requests to the default branch, on
               pull_request or pull_request_target, is not a required check
  ORPHANED     a required check is a context no such job produces. A job that
               runs only on merge_group, push, on pull requests to other
               branches, or in a workflow that is not `active` does not count:
               the context never reports on the PR head
  TRIGGER      a required job's pull_request (or pull_request_target) `types:`
               omit opened or synchronize, so it does not report on every pull
               request head
  CONDITIONAL  a required job can be skipped, and GitHub reports a skipped job as
               success: it has a job-level `if:`, or something in its `needs:`
               chain has one or is not itself required. When the skipped job calls
               a reusable workflow, its '<caller> / <called>' contexts never
               report at all, and the merge waits on them instead
  PATH-FILTER  a required job is path-filtered, so it never reports on an
               unrelated pull request and blocks it forever (AGENTS.md 3.2)
  DUPLICATE    a required job's workflow also runs on push to some branch other
               than the default: no branch filter, a branches-ignore that leaves
               one, or branches that match one. A pull request head then carries
               the context from two suites, and the merge takes either
               (kindspec/rowspec#43). A tags-only push does not count. For a
               called workflow's contexts, the caller's push decides. The same
               holds when the push producer is a job in another active workflow
               whose push admits such a branch: its context ('<caller> /
               <called>' for a call), by `name:` or else its id, equals the
               required one. Its `if:` does not matter: a skipped job still
               reports its context. Likewise when a second producer runs on the
               pull request itself: the required job's workflow runs on both
               pull_request and pull_request_target, or another active workflow
               runs a job of the same context on either, into the default
               branch. That pair is reported once, from the first workflow by path
  STALE-ALLOW  an ALLOW entry matches no job any more

pull_request_target counts as a pull request event: its check runs carry the
pull request's head sha, and GitHub lists it among the events whose checks
satisfy a required status check (kindspec/.github#20). It runs the workflow file
from the base branch, with GITHUB_SHA the base's last commit, so a pull request
cannot change what such a job does, and the job tests the pull request's code
only if it checks that out. A pull_request_target job that is meant to gate
nothing, such as a labeller, belongs in ALLOW with that reason.

Exit 0 clean, 1 on any finding, 2 when something could not be evaluated: no
repositories read; an API or authentication failure; fewer repositories listed
than the org reports, or a private count this token cannot read; a repository
whose rules or workflow states cannot be read (rulesets on a private repository
need a paid plan); a workflow the parser cannot read or GitHub would reject
(a job with neither runs-on nor uses, or uses with runs-on or steps, a
non-mapping job); a matrix,
expression- or block-named job whose context names this script does not expand;
or, for a required job, a push branch filter this script cannot settle either
way (it decides by finding a branch the filter admits, or by enumerating every
branch it could), in its own workflow or in another whose job has the same
context; or a job of another workflow that runs on such a push, or on a pull
request into the default branch, and whose context is not known (matrix,
expression or block name, or a call not read).
A run that could not look must not report a pass.

A job that calls a reusable workflow (`uses: ./.github/workflows/F.yml`, or
`uses: OWNER/REPO/.github/workflows/F.yml@REF`) produces one context per called
job, '<caller job> / <called job>', each named by its `name:` or else its id.
The caller's triggers, `if:` and `needs:` gate all of them; each called job's
own `if:` and `needs:` gate it too. A local call is read from the same
default-branch snapshot as the caller; any other is fetched at exactly REF and
kept in the snapshot under "called". Not evaluated (exit 2): a call that
cannot be fetched or is not in the snapshot, any other `uses:` form, a called
workflow with no workflow_call trigger or that cannot be parsed, and a called
job that itself calls a workflow or is matrix-, expression- or block-named.

Reads every repository in the org that the caller can see, through the `gh`
CLI: workflow files on the default branch, the workflows their jobs call, the
rules that apply to that branch (GET /repos/{o}/{r}/rules/branches/{b}) and
classic branch protection.
--public-only skips private repositories and says how many it skipped, or that
it cannot tell when the token cannot see the org's private count.

    python3 scripts/check_required_checks.py [--org kindspec] [--public-only]
    python3 scripts/check_required_checks.py --save snap.json   # also write what was read
    python3 scripts/check_required_checks.py --load snap.json   # evaluate a snapshot offline
    python3 scripts/check_required_checks.py --selftest         # each finding must fire
"""

import argparse
import base64
import itertools
import json
import re
import subprocess
import sys
import urllib.parse

# Jobs that run on pull requests but deliberately gate nothing, as
# (repo, workflow path, job id): reason. Jobs that never run on a pull request
# (rowspec's release.yml: gate, build, publish run on v* tags) are excluded by
# their triggers and need no entry here.
ALLOW = {}

ACTIONS_APP_ID = 15368  # GitHub Actions; a context from another app is not a workflow job
DEFAULT_TYPES = {"opened", "synchronize"}  # without both, a PR head can go unreported
# Events whose check runs attach to a pull request's head commit and count toward its
# required checks. pull_request_target runs the base branch's workflow, but its check
# runs still carry the head sha (kindspec/.github#20).
PR_EVENTS = ("pull_request", "pull_request_target")
SAMPLES = 4096  # names tried per branch filter pattern; a pattern with more is not enumerated
GH = ["gh"]


class Unsupported(Exception):
    pass


class Unreadable(Exception):
    pass


# --- a YAML subset: block mappings and sequences, flow lists, block scalars ---


def _strip_comment(s):
    quote = None
    for i, c in enumerate(s):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _lines(text):
    out, raw = [], text.splitlines()
    i = 0
    while i < len(raw):
        line = raw[i]
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise Unsupported("tab indentation")
        body = _strip_comment(line.strip())
        i += 1
        if not body or (body == "---" and not out):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if re.search(r"(^-|:)\s*[|>][-+0-9]*$", body):  # block scalar: skip its body
            body = re.sub(r"[|>][-+0-9]*$", "<block>", body)
            while i < len(raw) and (
                not raw[i].strip() or len(raw[i]) - len(raw[i].lstrip(" ")) > indent
            ):
                i += 1
        out.append((indent, body))
    return out


def _scalar(v):
    v = v.strip()
    if v[:1] in "&*!" or v.startswith("? "):
        raise Unsupported(f"anchors, aliases and tags: {v!r}")
    if v[:1] == "[":
        if not v.endswith("]") or "[" in v[1:-1] or "{" in v[1:-1]:
            raise Unsupported(f"flow sequence: {v!r}")
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    if v[:1] == "{":
        if v.replace(" ", "") != "{}":
            raise Unsupported(f"flow mapping: {v!r}")
        return {}
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _split_key(body):
    m = re.match(r"""^("[^"]*"|'[^']*'|[^'"\s][^:]*?)\s*:(\s+(.*))?$""", body)
    if not m:
        return None
    return _scalar(m.group(1)), (m.group(3) or "")


def _block(lines, i, indent):
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        seq = []
        while (
            i < len(lines)
            and lines[i][0] == indent
            and (lines[i][1] == "-" or lines[i][1].startswith("- "))
        ):
            rest = lines[i][1][1:].strip()
            if not rest:
                i += 1
                if i < len(lines) and lines[i][0] > indent:
                    item, i = _block(lines, i, lines[i][0])
                else:
                    item = None
            elif _split_key(rest) and not rest.startswith(("'", '"', "[", "{")):
                lines[i] = (indent + 2, rest)
                item, i = _block(lines, i, indent + 2)
            else:
                item, i = _scalar(rest), i + 1
            seq.append(item)
        return seq, i
    mapping = {}
    while i < len(lines) and lines[i][0] == indent:
        kv = _split_key(lines[i][1])
        if kv is None or lines[i][1].startswith("- "):
            raise Unsupported(f"cannot read line: {lines[i][1]!r}")
        key, value = kv
        i += 1
        if value:
            mapping[key] = _scalar(value)
        elif i < len(lines) and (
            lines[i][0] > indent or (lines[i][0] == indent and lines[i][1].startswith("-"))
        ):
            mapping[key], i = _block(lines, i, lines[i][0])
        else:
            mapping[key] = None
    return mapping, i  # a stray deeper line stops the parse; parse_yaml refuses it


def parse_yaml(text):
    lines = _lines(text)
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise Unsupported(f"stopped at {lines[i][1]!r}")
    return value


# --- evaluation ---


def _pattern(pattern):
    """A GitHub filter pattern as (regex, sample names, whether the samples are all it matches).

    `*` is any run without '/', `**` any run, `?` zero or one and `+` one or more of
    the preceding character, `[...]` one character from a set of letters, digits
    and ranges among them, and backslash escapes. Anything else is refused.

    Matching is case-sensitive; GitHub does not document whether its own is. A
    pattern with many `**` and no match, such as `a**a**...a**b`, backtracks for
    tens of seconds at around twenty; the audit job's timeout bounds that.
    """
    atoms, i = [], 0  # (regex, samples, finite, a character ? or + may follow)
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            atoms.append((".*", ["", "x", "x/x"], False, False))
            i += 1
        elif c == "*":
            atoms.append(("[^/]*", ["", "x"], False, False))
        elif c in "?+":
            if not atoms or not atoms[-1][3]:
                raise Unsupported(f"filter pattern {pattern!r}: '{c}' follows no character")
            r, s, finite, _ = atoms.pop()
            if c == "?":
                atoms.append((f"(?:{r})?", ["", *s], finite, False))
            else:
                atoms.append((f"(?:{r})+", [*s, *(x + x for x in s)], False, False))
        elif c == "[":
            end = pattern.find("]", i)
            body = pattern[i + 1 : end]
            if end < 0 or not re.fullmatch(r"(?:[A-Za-z0-9](?:-[A-Za-z0-9])?)+", body):
                raise Unsupported(f"filter pattern {pattern!r}: character set")
            chars = set()
            for lo, hi in re.findall(r"([A-Za-z0-9])(?:-([A-Za-z0-9]))?", body):
                hi = hi or lo
                if lo > hi or not any(
                    f(lo) and f(hi) for f in (str.isdigit, str.islower, str.isupper)
                ):
                    raise Unsupported(f"filter pattern {pattern!r}: range {lo}-{hi}")
                chars |= {chr(n) for n in range(ord(lo), ord(hi) + 1)}
            atoms.append(("[" + "".join(sorted(chars)) + "]", sorted(chars), True, True))
            i = end
        elif c == "]":
            raise Unsupported(f"filter pattern {pattern!r}: unmatched ']'")
        else:
            if c == "\\":
                i += 1
                if i == len(pattern):
                    raise Unsupported(f"filter pattern {pattern!r}: trailing backslash")
                c = pattern[i]
            atoms.append((re.escape(c), [c], True, True))
        i += 1
    regex = re.compile("".join(a[0] for a in atoms) + r"\Z")
    samples = itertools.islice(itertools.product(*(a[1] for a in atoms)), SAMPLES + 1)
    samples = ["".join(t) for t in samples]
    return regex, samples[:SAMPLES], all(a[2] for a in atoms) and len(samples) <= SAMPLES


def _glob(pattern):
    if re.search(r"[?+\[\]]", pattern):
        raise Unsupported(f"branch filter pattern {pattern!r}")
    return _pattern(pattern)[0]


def _patterns(config, key):
    value = config[key]
    if value is None or isinstance(value, dict):
        raise Unsupported(f"push {key}: {value!r}")
    return [str(p) for p in (value if isinstance(value, list) else [value])]


def _branch_name(name):
    # Only empty segments are ruled out. Other names git refuses, such as
    # 'main.lock' or 'x..y', still count as witnesses: this errs toward a finding.
    return bool(name) and "//" not in f"/{name}/"


def push_duplicates(on, branch):
    """Why the push trigger also runs on a branch other than branch, or None.

    A pull request head is such a branch, so its required contexts would then come
    from two suites. Decided by finding a branch the trigger admits, or by showing
    there is none; a filter this cannot settle either way is refused.
    """
    if "push" not in on:
        return None
    config = on["push"] if on["push"] is not None else {}
    if not isinstance(config, dict):
        raise Unsupported(f"unreadable push trigger: {config!r}")
    refs = {"branches", "branches-ignore", "tags", "tags-ignore"} & set(config)
    if not refs:
        return "push has no branch filter"
    if {"branches", "branches-ignore"} <= refs:
        raise Unsupported("push has both branches and branches-ignore; GitHub rejects it")
    others = ["x", "x/x", "X", "0", "x-x", "x.x", "x_x", f"{branch}x", f"x/{branch}"]
    if "branches-ignore" in config:
        ignore = _patterns(config, "branches-ignore")
        if any(p.startswith("!") for p in ignore):
            # GitHub documents '!' for branches, not for branches-ignore
            raise Unsupported(f"push branches-ignore {ignore}: a negated pattern")
        if any(re.fullmatch(r"\**\*\*\**", p) for p in ignore):
            return None  # a pattern of only stars, '**' among them, ignores every branch
        regexes = [_pattern(p)[0] for p in ignore]
        for name in others:
            if not any(r.match(name) for r in regexes):
                return f"push branches-ignore admits '{name}'"
        raise Unsupported(f"push branches-ignore {ignore}: cannot tell what it admits")
    if "branches" not in config:
        return None  # tags only
    filters, settled = [], True
    patterns = _patterns(config, "branches")
    if not patterns:
        raise Unsupported("push branches: [] is not documented to mean anything")
    for n, p in enumerate(patterns):
        negated = p.startswith("!")
        regex, samples, finite = _pattern(p[1:] if negated else p)
        filters.append((negated, regex))
        if not negated:
            others += samples
            # every name it matches is sampled, or a later '!**' drops them all
            settled &= finite or any(re.fullmatch(r"!\**\*\*\**", q) for q in patterns[n:])
    for name in others:
        runs = False
        for negated, regex in filters:
            if regex.match(name):
                runs = not negated
        if runs and name != branch and _branch_name(name):
            return f"push branches admit '{name}'"
    if settled:
        return None
    raise Unsupported(f"push branches {patterns}: cannot tell what they admit")


def _branch_runs(config, branch):
    """Whether a pull_request trigger with this config runs for PRs into branch."""
    if not isinstance(config, dict):
        return True
    patterns = config.get("branches")
    ignore = config.get("branches-ignore")
    if ignore is not None:
        ignore = ignore if isinstance(ignore, list) else [ignore]
        return not any(_glob(str(p)).match(branch) for p in ignore)
    if patterns is None:
        return True
    runs = False
    for p in patterns if isinstance(patterns, list) else [patterns]:
        p = str(p)
        if p.startswith("!"):
            if _glob(p[1:]).match(branch):
                runs = False
        elif _glob(p).match(branch):
            runs = True
    return runs


def _events(workflow):
    if not isinstance(workflow, dict):
        raise Unsupported(f"workflow is not a mapping: {type(workflow).__name__}")
    on = workflow.get("on")
    if isinstance(on, str):
        on = [on]
    if isinstance(on, list):
        on = {e: None for e in on}
    if not isinstance(on, dict):
        raise Unsupported(f"unreadable 'on': {on!r}")
    return on


def pr_events(on, branch):
    """The events in PR_EVENTS on which the workflow runs for a pull request into branch."""
    return [e for e in PR_EVENTS if e in on and _branch_runs(on[e], branch)]


def pr_admits(on, branch):
    """Why the workflow reports on a pull request into branch, or None; for producers()."""
    events = pr_events(on, branch)
    return "on " + " and ".join(events) if events else None


def pr_trigger(workflow, branch):
    """(events that reach a PR into branch, path-filtered, restricted types, why not)."""
    on = _events(workflow)
    events = pr_events(on, branch)
    if not events:
        why = "; ".join(f"{e} excludes '{branch}'" for e in PR_EVENTS if e in on)
        others = [e for e in ("merge_group", "push") if e in on]
        why = why or ("only " + ", ".join(others) if others else None)
        return [], False, None, why
    # a filter or a types: restriction matters only if every event that reaches the PR
    # has one; otherwise another event reports the context on every head
    configs = [on[e] if isinstance(on[e], dict) else {} for e in events]
    filtered = all({"paths", "paths-ignore"} & set(c) for c in configs)
    types = [c.get("types") for c in configs]
    types = [None if t is None else set(map(str, t if isinstance(t, list) else [t])) for t in types]
    restricted = None
    if not any(t is None or DEFAULT_TYPES <= t for t in types):
        restricted = sorted(set().union(*types))
    return events, filtered, restricted, None


def jobs_of(workflow):
    """Yield (job id, context, if, needs, unresolved reason, uses)."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise Unsupported(f"'jobs' is not a mapping: {jobs!r}")
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            raise Unsupported(f"job '{job_id}' is not a mapping: {job!r}")
        if "runs-on" not in job and "uses" not in job:
            raise Unsupported(f"job '{job_id}' has neither runs-on nor uses; GitHub rejects it")
        if "uses" in job and {"runs-on", "steps"} & set(job):
            raise Unsupported(f"job '{job_id}' has uses with runs-on or steps; GitHub rejects it")
        context = str(job.get("name", job_id))
        unresolved = None
        if isinstance(job.get("strategy"), dict) and "matrix" in job["strategy"]:
            unresolved = "matrix job; contexts are expanded per combination"
        elif "${{" in context:
            unresolved = "name is an expression"
        elif context == "<block>":
            unresolved = "name is a block scalar"
        needs = job.get("needs") or []
        needs = needs if isinstance(needs, list) else [needs]
        uses = str(job["uses"]) if "uses" in job else None
        yield job_id, context, "if" in job, [str(n) for n in needs], unresolved, uses


# A called workflow's jobs report as '<caller job> / <called job>', each named by
# its `name:` or else its id. One level deep: a called job that itself calls a
# workflow is refused.
LOCAL_CALL = re.compile(r"\./(\.github/workflows/[^/@]+\.ya?ml)\Z")
REMOTE_CALL = re.compile(r"([\w.-]+)/([\w.-]+)/(\.github/workflows/[^/@]+\.ya?ml)@([^\s@]+)\Z")


def expand(context, uses, data):
    """({called job id: job tuple named '<context> / <called>'}, None), or (None, why not)."""
    m = LOCAL_CALL.match(uses)
    if m:
        text = data["workflows"].get(m.group(1))
        if text is None:
            return None, f"calls {uses}, which is not among this repository's workflows"
    elif REMOTE_CALL.match(uses):
        text = (data.get("called") or {}).get(uses)
        if text is None:
            return None, f"calls {uses}, which the snapshot does not hold"
        if not isinstance(text, str):
            return None, f"calls {uses}, which could not be read: {text.get('unreadable')}"
    else:
        return None, f"calls {uses!r}, which is not a workflow reference this script reads"
    try:
        workflow = parse_yaml(text)
        if "workflow_call" not in _events(workflow):
            return None, f"calls {uses}, which has no workflow_call trigger"
        called = {}
        for cid, cname, has_if, needs, unresolved, nested in jobs_of(workflow):
            if nested:
                return None, f"calls {uses}, whose job '{cid}' calls another workflow"
            if unresolved:
                return None, f"calls {uses}, whose job '{cid}' is not read: {unresolved}"
            called[cid] = (cid, f"{context} / {cname}", has_if, needs, None, None)
    except Unsupported as e:
        return None, f"calls {uses}, which cannot be read: {e}"
    return called, None


def producers(data, branch, admits):
    """The contexts each active workflow produces where admits(on, branch) gives a reason.

    With push_duplicates, that is on push to a branch other than branch; with pr_admits,
    on a pull request into branch.
    Returns ({context: [(path, producing job, why)]}, [(path, context, why not evaluated)]),
    where a context of None could be any. A job's `if:` does not matter: a skipped job
    still reports its context. A workflow that cannot be read is refused by evaluate.
    """
    found, unknown = {}, []
    for path, text in sorted(data["workflows"].items()):
        if data["workflow_state"].get(path) != "active":
            continue
        try:
            workflow = parse_yaml(text)
            on = _events(workflow)
            jobs = list(jobs_of(workflow))
        except Unsupported:
            continue
        try:
            why, doubt = admits(on, branch), None
        except Unsupported as e:
            why, doubt = None, str(e)
        if not why and not doubt:
            continue
        for job_id, context, _, _, unresolved, uses in jobs:
            units = [(f"job '{job_id}'", context)]
            if uses and not unresolved:
                called, unresolved = expand(context, uses, data)
                units = [
                    (f"job '{job_id}' (called job '{c}')", j[1]) for c, j in (called or {}).items()
                ]
            if unresolved:
                unknown.append((path, None, f"job '{job_id}': {unresolved}"))
                continue
            for job, context in units:
                if doubt:
                    unknown.append((path, context, doubt))
                else:
                    found.setdefault(context, []).append((path, job, why))
    return found, unknown


def _skippable(job_id, jobs, required, calls, seen=frozenset()):
    """Why job_id can be skipped on a pull request, or None."""
    if jobs[job_id][2]:
        return "job-level if:"
    for n in jobs[job_id][3]:
        if n not in jobs:
            return f"needs '{n}', which is not a job in this workflow"
        if n in seen:
            continue
        if jobs[n][4]:
            return f"needs '{n}', which was not evaluated"
        inner = calls.get(n, {})
        contexts = [c[1] for c in inner.values()] if n in calls else [jobs[n][1]]
        if any(c not in required for c in contexts):
            return f"needs '{n}', which is not required: if it fails, this job is skipped"
        why = _skippable(n, jobs, required, calls, seen | {job_id})
        for cid in inner:
            why = why or _skippable(cid, inner, required, {})
        if why:
            return f"needs '{n}' ({why})"
    return None


def evaluate(snapshot, allow):
    findings, incomplete, used = [], [], set()
    stats = {"repos": 0, "workflows": 0, "pr_jobs": 0, "required": 0}
    for repo, data in sorted(snapshot.items()):
        if data.get("unreadable"):
            incomplete.append(f"{repo}: not evaluated: {data['unreadable']}")
            continue
        if "default_branch" not in data:
            incomplete.append(f"{repo}: not evaluated: snapshot has no default_branch")
            continue
        if "workflow_state" not in data:
            incomplete.append(f"{repo}: not evaluated: snapshot has no workflow_state")
            continue
        stats["repos"] += 1
        branch = data["default_branch"]
        required = {}
        for c in data["required"]:
            required.setdefault(c["context"], c.get("integration_id"))
        stats["required"] += len(required)
        produced, elsewhere, blind = set(), {}, False
        on_push, push_unknown = producers(data, branch, push_duplicates)
        on_pr, pr_unknown = producers(data, branch, pr_admits)
        for path, text in sorted(data["workflows"].items()):
            stats["workflows"] += 1
            state = data["workflow_state"].get(path)
            if state is None:
                incomplete.append(f"{repo}: {path}: not evaluated: no workflow state")
                blind = True
                continue
            try:
                workflow = parse_yaml(text)
                events, filtered, types, why = pr_trigger(workflow, branch)
                jobs = {j[0]: j for j in jobs_of(workflow)}
            except Unsupported as e:
                incomplete.append(f"{repo}: {path}: not evaluated: {e}")
                blind = True
                continue
            if state != "active":
                events, why = [], f"workflow is {state}"
            if not events:
                for _, context, *_ in jobs.values():
                    if why:
                        elsewhere.setdefault(context, why)
                continue
            try:
                pushed, unknown = push_duplicates(_events(workflow), branch), None
            except Unsupported as e:
                pushed, unknown = None, str(e)
            calls = {}
            for job_id, job in jobs.items():
                if job[5] and not job[4]:
                    called, unresolved = expand(job[1], job[5], data)
                    if unresolved:
                        jobs[job_id] = (*job[:4], unresolved, job[5])
                    else:
                        calls[job_id] = called
            for job_id, context, _, _, unresolved, _ in jobs.values():
                where = f"{repo}: {path}: job '{job_id}'"
                if (repo, path, job_id) in allow:
                    stats["pr_jobs"] += 1
                    used.add((repo, path, job_id))
                    continue
                if unresolved:
                    stats["pr_jobs"] += 1
                    incomplete.append(f"{where}: not evaluated: {unresolved}")
                    blind = True
                    continue
                if job_id in calls:
                    units = [
                        (f"{where} (called job '{cid}')", c[1], cid, calls[job_id])
                        for cid, c in calls[job_id].items()
                    ]
                else:
                    units = [(where, context, None, None)]
                for unit, context, cid, inner in units:
                    stats["pr_jobs"] += 1
                    produced.add(context)
                    if context not in required:
                        findings.append(
                            f"UNGATED      {unit} runs on pull requests; "
                            f"'{context}' is not a required check"
                        )
                        continue
                    if pushed:
                        findings.append(
                            f"DUPLICATE    {unit} is required and its workflow also runs on push "
                            f"to other branches ({pushed}), so a pull request head can carry "
                            f"'{context}' from two suites and the merge takes either"
                        )
                    elif unknown:
                        incomplete.append(f"{unit}: not evaluated for a push producer: {unknown}")
                    if len(events) > 1:
                        findings.append(
                            f"DUPLICATE    {unit} is required and its workflow runs on both "
                            f"{' and '.join(events)}, so a pull request head can carry "
                            f"'{context}' from two suites and the merge takes either"
                        )
                    # one finding per pair of workflows, from the first in path order
                    for other, job, why in on_pr.get(context, []):
                        if other > path:
                            findings.append(
                                f"DUPLICATE    {unit} is required, and {other}: {job} also "
                                f"produces '{context}' on a pull request into '{branch}' ({why}), "
                                "so a pull request head can carry it from two suites and the "
                                "merge takes either"
                            )
                    # its own push is reported above; another workflow's push is this one
                    for other, job, why in on_push.get(context, []):
                        if other != path:
                            findings.append(
                                f"DUPLICATE    {unit} is required, and {other}: {job} also "
                                f"produces '{context}' on push to other branches ({why}), so a "
                                "pull request head can carry it from two suites and the merge "
                                "takes either"
                            )
                    doubts = [
                        f"{other}: {why}"
                        for other, c, why in push_unknown
                        if other != path and c in (None, context)
                    ]
                    if doubts:
                        incomplete.append(
                            f"{unit}: not evaluated for a push producer in another workflow: "
                            + "; ".join(doubts)
                        )
                    doubts = [
                        f"{other}: {why}"
                        for other, c, why in pr_unknown
                        if other != path and c in (None, context)
                    ]
                    if doubts:
                        incomplete.append(
                            f"{unit}: not evaluated for a pull request producer in another "
                            "workflow: " + "; ".join(doubts)
                        )
                    if filtered:
                        findings.append(
                            f"PATH-FILTER  {unit} is required but its pull_request "
                            "trigger is path-filtered"
                        )
                    if types:
                        findings.append(
                            f"TRIGGER      {unit} is required but pull_request types {types} "
                            "omit opened or synchronize"
                        )
                    skip = _skippable(job_id, jobs, required, calls)
                    effect = "can be skipped, which reports success"
                    if cid and skip:
                        # GitHub reports the skipped caller under its own name; the
                        # '<caller> / <called>' context never appears at all.
                        effect = "is never reported when its caller is skipped, so the merge waits"
                    elif cid:
                        skip = _skippable(cid, inner, required, {})
                    if skip:
                        findings.append(f"CONDITIONAL  {unit} is required but {effect}: {skip}")
        for context, app in sorted(required.items()):
            if app not in (None, ACTIONS_APP_ID):
                incomplete.append(
                    f"{repo}: required '{context}' comes from app {app}, not a workflow"
                )
            elif context not in produced and blind:
                incomplete.append(
                    f"{repo}: required '{context}' not matched, and a job above was not read"
                )
            elif context not in produced:
                note = f" ({elsewhere[context]})" if context in elsewhere else ""
                findings.append(
                    f"ORPHANED     {repo}: required check '{context}' is produced by no "
                    f"job that reports on a pull request into '{branch}'{note}"
                )
    for key in sorted(set(allow) - used):
        findings.append(f"STALE-ALLOW  {key} matches no pull_request job")
    if stats["repos"] == 0:
        incomplete.append("no repositories were evaluated")
    return findings, incomplete, stats


def exit_code(findings, incomplete):
    return 1 if findings else 2 if incomplete else 0


# --- collection ---


def gh(path):
    try:
        r = subprocess.run(
            [*GH, "api", "--paginate", path], capture_output=True, text=True, check=False
        )
    except OSError as e:
        raise Unreadable(f"cannot run {GH[0]}: {e}") from e
    if r.returncode != 0:
        if "HTTP 404" in r.stderr:
            return None
        raise Unreadable(f"gh api {path} failed: {r.stderr.strip() or r.returncode}")
    try:
        # --paginate concatenates JSON arrays as ][
        out = r.stdout.strip()
        return json.loads(re.sub(r"\]\s*\[", ",", out) if out.startswith("[") else out)
    except ValueError as e:
        raise Unreadable(f"gh api {path}: not JSON: {e}") from e


def collect(org, public_only=False, api=gh):
    repos = api(f"orgs/{org}/repos?per_page=100")
    if not isinstance(repos, list):
        raise Unreadable(f"cannot list repositories of '{org}'")
    snapshot, skipped = {}, 0
    org_info = api(f"orgs/{org}") or {}
    listed_public = sum(1 for r in repos if not r["private"])
    listed_private = len(repos) - listed_public
    public, private = org_info.get("public_repos"), org_info.get("total_private_repos")
    problems = []
    if public is None or listed_public < public:
        problems.append(f"listed {listed_public} public repositories; the org reports {public}")
    if public_only:
        skipped = None if private is None else max(private, listed_private)
    elif private is None:
        problems.append(
            "this token cannot see the org's private repository count, so a private "
            "repository may be missing unseen; use --public-only to check public ones"
        )
    elif listed_private < private:
        problems.append(f"listed {listed_private} private repositories; the org reports {private}")
    if problems:
        snapshot["(org)"] = {"unreadable": "; ".join(problems)}
    for repo in repos:
        if repo["archived"]:
            continue
        if public_only and repo["private"]:
            continue
        name, branch = repo["name"], repo["default_branch"]
        try:
            workflows = {}
            listing = api(f"repos/{org}/{name}/contents/.github/workflows?ref={branch}")
            for entry in listing or []:
                if entry["type"] == "file" and entry["name"].endswith((".yml", ".yaml")):
                    blob = api(f"repos/{org}/{name}/contents/{entry['path']}?ref={branch}")
                    workflows[entry["path"]] = base64.b64decode(blob["content"]).decode()
            called = {}
            for uses in sorted({u for text in workflows.values() for u in _remote_calls(text)}):
                called[uses] = _fetch_call(uses, api)
            runs = api(f"repos/{org}/{name}/actions/workflows?per_page=100")
            if not isinstance(runs, dict):
                raise Unreadable("cannot read workflow states")
            state = {w["path"]: w["state"] for w in runs.get("workflows", [])}
            rules = api(f"repos/{org}/{name}/rules/branches/{branch}")
            if rules is None:
                raise Unreadable(f"no rules endpoint for '{branch}'")
            required = []
            for rule in rules:
                if rule["type"] == "required_status_checks":
                    required += rule["parameters"]["required_status_checks"]
            protection = (api(f"repos/{org}/{name}/branches/{branch}") or {}).get("protection")
            for c in ((protection or {}).get("required_status_checks") or {}).get("checks", []):
                required.append({"context": c["context"], "integration_id": c.get("app_id")})
        except Unreadable as e:
            snapshot[name] = {"unreadable": str(e)}
            continue
        snapshot[name] = {
            "workflows": workflows,
            "required": required,
            "default_branch": branch,
            "workflow_state": state,
            "called": called,
        }
    return snapshot, skipped


def _remote_calls(text):
    """The other-repository workflows a workflow's jobs call; evaluate refuses what this skips."""
    try:
        jobs = parse_yaml(text).get("jobs")
    except (Unsupported, AttributeError):
        return []
    if not isinstance(jobs, dict):
        return []
    return [
        j["uses"]
        for j in jobs.values()
        if isinstance(j, dict) and isinstance(j.get("uses"), str) and REMOTE_CALL.match(j["uses"])
    ]


def _fetch_call(uses, api):
    """The called workflow's text at exactly the ref in `uses`, or {'unreadable': why}."""
    owner, repo, path, ref = REMOTE_CALL.match(uses).groups()
    try:
        blob = api(f"repos/{owner}/{repo}/contents/{path}?ref={urllib.parse.quote(ref, safe='')}")
    except Unreadable as e:
        return {"unreadable": str(e)}
    if not isinstance(blob, dict) or "content" not in blob:
        return {"unreadable": f"no file {path} in {owner}/{repo} at {ref}"}
    return base64.b64decode(blob["content"]).decode()


def run_live(org, public_only, save=None):
    """Collect and evaluate. Returns (findings, incomplete, stats, skipped)."""
    try:
        snapshot, skipped = collect(org, public_only)
    except Unreadable as e:
        return [], [str(e)], {"repos": 0, "workflows": 0, "pr_jobs": 0, "required": 0}, None
    if save:
        with open(save, "w") as fh:
            json.dump(snapshot, fh, indent=1, sort_keys=True)
    return (*evaluate(snapshot, ALLOW), skipped)


# --- self-test: every finding and every refusal must be seen to fire ---

# push on the default branch only, as kindkit#26 and rowspec#67 left them: one
# producer per context on a pull request head
_ON = "on:\n  push:\n    branches: [main]\n  pull_request:\n"
_PR = _ON + "jobs:\n  {job}:\n    runs-on: x\n"
_CHECK = [{"context": "check", "integration_id": ACTIONS_APP_ID}]


def _on(trigger):
    return f"on:\n{trigger}jobs:\n  check:\n    runs-on: x\n"


def _fake_api(responses):
    """A key holding '?' answers only that exact path, query included."""

    def api(path):
        base = path.split("?")[0]
        if "?" in path and path in responses:
            base = path
        keys = [k for k in responses if k == base] or sorted(
            (k for k in responses if base.startswith(k)), key=len, reverse=True
        )
        value = responses[keys[0]] if keys else None
        if isinstance(value, Exception):
            raise value
        return value

    return api


def selftest():
    def run(snapshot, allow=None):
        try:
            f, inc, _ = evaluate(snapshot, allow or {})
        except Exception as e:  # noqa: BLE001 -- a crash is a failed case
            return [f"CRASH {type(e).__name__}"], -1
        return [x.split()[0] for x in f] + ["INCOMPLETE"] * len(inc), exit_code(f, inc)

    def repo(wf, required=_CHECK, more=None, state="active", called=None):
        workflows = {"w.yml": wf, **(more or {})}
        states = {path: state for path in workflows}
        data = {
            "workflows": workflows,
            "required": required,
            "default_branch": "main",
            "workflow_state": states,
        }
        if called is not None:
            data["called"] = called
        return {"r": data}

    def live(responses, public_only=False):
        try:
            snap, skipped = collect("o", public_only, api=_fake_api(responses))
            snap = json.loads(json.dumps(snap))  # what --save writes is what --load reads
        except Unreadable as e:
            return ["INCOMPLETE"], 2, str(e)
        except Exception as e:  # noqa: BLE001
            return [f"CRASH {type(e).__name__}"], -1, None
        got, code = run(snap)
        return got, code, skipped

    tags = "on:\n  push:\n    tags: ['v*']\njobs:\n  gate:\n    runs-on: x\n    steps:\n      - run: |\n          x\n"
    extra = "  extra:\n    runs-on: x\n"
    inc2 = ["INCOMPLETE", "INCOMPLETE"]

    # reusable workflows: kindkit's kind.yml, called locally and by a pinned ref
    local, remote = "./.github/workflows/k.yml", "kindspec/kindkit/.github/workflows/kind.yml@abc1"
    remote2 = remote.replace("@abc1", "@def2")
    kind = [{"context": "kind / conformance", "integration_id": ACTIONS_APP_ID}]

    def caller(uses, more=""):
        return f"{_ON}jobs:\n  kind:\n{more}    uses: {uses}\n"

    def called(jobs):
        return "on:\n  workflow_call:\n    inputs:\n      x:\n        type: string\njobs:\n" + jobs

    conf = called("  conformance:\n    runs-on: x\n")
    needs_kind = _PR.format(job="check") + "    needs: kind\n" + caller(remote).split("jobs:\n")[1]
    reusable = [
        (
            "local reusable workflow expands to '<caller> / <called>'",
            repo(caller(local), kind, more={".github/workflows/k.yml": conf}),
            [],
            None,
        ),
        (
            "remote reusable workflow expands from the snapshot",
            repo(caller(remote), kind, called={remote: conf}),
            [],
            None,
        ),
        (
            "caller and called names make the context",
            repo(
                caller(remote, "    name: K\n"),
                [{"context": "K / C"}],
                called={remote: called("  c:\n    name: C\n    runs-on: x\n")},
            ),
            [],
            None,
        ),
        (
            "unrequired called job",
            repo(caller(remote), kind, called={remote: conf + extra}),
            ["UNGATED"],
            None,
        ),
        (
            "required context no called job produces",
            repo(caller(remote), kind + [{"context": "kind / gone"}], called={remote: conf}),
            ["ORPHANED"],
            None,
        ),
        (
            "called job with an if:",
            repo(caller(remote), kind, called={remote: conf + "    if: false\n"}),
            ["CONDITIONAL"],
            None,
        ),
        (
            "caller job with an if:",
            repo(caller(remote, "    if: false\n"), kind, called={remote: conf}),
            ["CONDITIONAL"],
            None,
        ),
        (
            "called job needs an unrequired called job",
            repo(
                caller(remote),
                kind,
                called={remote: conf + "    needs: b\n  b:\n    runs-on: x\n"},
            ),
            ["UNGATED", "CONDITIONAL"],
            None,
        ),
        (
            "needs a caller whose called jobs are all required is clean",
            repo(needs_kind, _CHECK + kind, called={remote: conf}),
            [],
            None,
        ),
        (
            "needs a caller with an unrequired called job",
            repo(needs_kind, _CHECK + kind, called={remote: conf + extra}),
            ["UNGATED", "CONDITIONAL"],
            None,
        ),
        (
            "needs a caller whose called job has an if:",
            repo(needs_kind, _CHECK + kind, called={remote: conf + "    if: false\n"}),
            ["CONDITIONAL", "CONDITIONAL"],
            None,
        ),
        (
            "remote call missing from the snapshot is not passed",
            repo(caller(remote), kind, called={}),
            inc2,
            None,
        ),
        (
            "snapshot without called workflows is not passed",
            repo(caller(remote), kind),
            inc2,
            None,
        ),
        (
            "unreadable called workflow is not passed",
            repo(caller(remote), kind, called={remote: {"unreadable": "HTTP 404"}}),
            inc2,
            None,
        ),
        (
            "missing local called workflow is not passed",
            repo(caller(local), kind),
            inc2,
            None,
        ),
        (
            "nested reusable workflow is not passed",
            repo(
                caller(remote),
                kind,
                called={
                    remote: called("  conformance:\n    uses: o/r/.github/workflows/x.yml@v1\n")
                },
            ),
            inc2,
            None,
        ),
        (
            "called job with an expression name is not passed",
            repo(
                caller(remote),
                kind,
                called={remote: called("  c:\n    name: ${{ inputs.x }}\n    runs-on: x\n")},
            ),
            inc2,
            None,
        ),
        (
            "called matrix job is not passed",
            repo(
                caller(remote),
                kind,
                called={remote: conf + "    strategy:\n      matrix:\n        v: [1, 2]\n"},
            ),
            inc2,
            None,
        ),
        (
            "called block-scalar name is not passed",
            repo(
                caller(remote),
                kind,
                called={remote: called("  c:\n    name: >-\n      conformance\n    runs-on: x\n")},
            ),
            inc2,
            None,
        ),
        (
            "called workflow without workflow_call is not passed",
            repo(
                caller(remote),
                kind,
                called={remote: "on: [push]\njobs:\n  conformance:\n    runs-on: x\n"},
            ),
            inc2,
            None,
        ),
        (
            "unparseable called workflow is not passed",
            repo(caller(remote), kind, called={remote: conf + "      stray: y\n"}),
            inc2,
            None,
        ),
        (
            "caller matrix is not passed",
            repo(
                caller(remote, "    strategy:\n      matrix:\n        v: [1]\n"),
                kind,
                called={remote: conf},
            ),
            inc2,
            None,
        ),
        (
            "unrecognised uses is not passed",
            repo(caller("o/r/ci/x.yml@v1"), kind, called={"o/r/ci/x.yml@v1": conf}),
            inc2,
            None,
        ),
        (
            "each call is read at its own ref",
            repo(
                caller(remote) + f"  kind2:\n    uses: {remote2}\n",
                kind + [{"context": "kind2 / conformance"}],
                called={remote: conf, remote2: conf.replace("conformance:", "conform:")},
            ),
            ["UNGATED", "ORPHANED"],
            None,
        ),
        (
            "path-filtered caller",
            repo(
                f"on:\n  pull_request:\n    paths: ['a/**']\njobs:\n  kind:\n    uses: {remote}\n",
                kind,
                called={remote: conf},
            ),
            ["PATH-FILTER"],
            None,
        ),
        (
            "caller on types: [labeled]",
            repo(
                f"on:\n  pull_request:\n    types: [labeled]\njobs:\n  kind:\n    uses: {remote}\n",
                kind,
                called={remote: conf},
            ),
            ["TRIGGER"],
            None,
        ),
        (
            "uses with runs-on is refused",
            repo(caller(remote, "    runs-on: x\n"), kind, called={remote: conf}),
            inc2,
            None,
        ),
        (
            "uses with steps is refused",
            repo(caller(remote, "    steps:\n      - run: x\n"), kind, called={remote: conf}),
            inc2,
            None,
        ),
    ]

    # a second producer: push runs on the pull request's branch as well (#16)
    def pushed(push, pr="  pull_request:\n"):
        return repo(_on(push + pr))

    def branches(*patterns, key="branches"):
        items = "".join(f"      - '{p}'\n" for p in patterns)
        return pushed(f"  push:\n    {key}:\n{items}")

    dup, inc1 = ["DUPLICATE"], ["INCOMPLETE"]
    duplicate = [
        (
            "on: [push, pull_request]",
            repo(_PR.format(job="check").replace(_ON, "on: [push, pull_request]\n")),
            dup,
        ),
        ("push: with no filter", pushed("  push:\n"), dup),
        ("push: {}", pushed("  push: {}\n"), dup),
        ("push filtered only by paths", pushed("  push:\n    paths: ['a/**']\n"), dup),
        (
            "tags and paths, no branch filter",
            pushed("  push:\n    tags: [v*]\n    paths: [a]\n"),
            [],
        ),
        ("tags-only push is not a producer", pushed("  push:\n    tags: ['v*']\n"), []),
        (
            "tags-ignore-only push is not a producer",
            branches("v*", key="tags-ignore"),
            [],
        ),
        ("push: branches: [main] is clean", branches("main"), []),
        (
            "push: branches: [main], tags",
            pushed("  push:\n    branches: [main]\n    tags: [v*]\n"),
            [],
        ),
        ("push: branches: main (scalar)", pushed("  push:\n    branches: main\n"), []),
        ("push: branches: ['**']", branches("**"), dup),
        ("push: branches: ['ma*'] admits max", branches("ma*"), dup),
        ("push: branches: ['releases/**']", branches("main", "releases/**"), dup),
        ("push: branches: [develop]", branches("main", "develop"), dup),
        ("push: branches: ['**', '!feature/**']", branches("**", "!feature/**"), dup),
        ("push: branches: ['**', '!**'] admits nothing", branches("**", "!**"), []),
        ("push: branches: ['**', '!**', 'x']", branches("**", "!**", "x"), dup),
        (
            "push: branches: [develop, '!develop']",
            branches("main", "develop", "!develop"),
            [],
        ),
        (
            "push: branches: ['!main', main]: last match wins",
            branches("!main", "main"),
            [],
        ),
        ("push: branches: ['[m]ain'] is main only", branches("[m]ain"), []),
        (
            "push: branches: ['[l-n]ain', ...] range",
            branches("[l-n]ain", "!lain", "!nain"),
            [],
        ),
        ("push: branches: ['[l-n]ain', '!lain']", branches("[l-n]ain", "!lain"), dup),
        ("push: branches: ['[a-c]x', '!ax', '!cx']", branches("[a-c]x", "!ax", "!cx"), dup),
        ("push: branches: ['[a-z0-9]x', '!*x']", branches("[a-z0-9]x", "!*x"), []),
        (
            "push: branches: ['main?', '!mai']: ? is zero or one",
            branches("main?", "!mai"),
            [],
        ),
        ("push: branches: ['main?']", branches("main?"), dup),
        ("push: branches: ['mai+n']: + is one or more", branches("mai+n"), dup),
        (
            "push: branches: ['main', 'main/'] names no branch",
            branches("main", "main/"),
            [],
        ),
        ("push: branches: 'ma\\in' escapes", branches("ma\\in"), []),
        ("push: branches-ignore: [main]", branches("main", key="branches-ignore"), dup),
        ("push: branches-ignore: ['**']", branches("**", key="branches-ignore"), []),
        (
            "push: branches-ignore: ['*'] admits x/x",
            branches("*", key="branches-ignore"),
            dup,
        ),
        (
            "push: branches-ignore: ['x', 'x/**']",
            branches("x", "x/**", key="branches-ignore"),
            dup,
        ),
        # each witness source must be tried: the generic names, and each pattern's samples
        ("push: only x/x is left", branches("*", "*/main", key="branches-ignore"), dup),
        ("push: only x/main is left", branches("*", "*/x", key="branches-ignore"), dup),
        ("push: only a '**' sample with a '/' is left", branches("a**", "!a*"), dup),
        ("push: only a '*' sampled empty is left", branches("ab*", "!abx"), dup),
        # cannot be decided this way: refused, never passed
        ("push: branches: ['*', '!*'] is refused", branches("*", "!*"), inc1),
        (
            "push: '!' in branches-ignore is refused",
            branches("**", "!feature/**", key="branches-ignore"),
            inc1,
        ),
        ("push: branches: [] is refused", pushed("  push:\n    branches: []\n"), inc1),
        (
            "push: branches-ignore: [] ignores nothing",
            pushed("  push:\n    branches-ignore: []\n"),
            dup,
        ),
        ("push: branches: ['!**', '*', '!*'] is refused", branches("!**", "*", "!*"), inc1),
        ("push: branches: ['mai+n', '!maiin'] is refused", branches("mai+n", "!maiin"), inc1),
        (
            "push: a finite filter past the sample cap is refused",
            branches("[a-z][a-z][a-z]", "![a-y]**"),
            inc1,
        ),
        (
            "push: branches-ignore: ['*', '*/**'] is refused",
            branches("*", "*/**", key="branches-ignore"),
            inc1,
        ),
        ("push: branches: ['[!m]ain'] is refused", branches("[!m]ain"), inc1),
        ("push: branches: ['[z-a]'] is refused", branches("main", "[z-a]"), inc1),
        ("push: branches: ['[A-z]'] is refused", branches("main", "[A-z]"), inc1),
        ("push: branches: ['?main'] is refused", branches("?main"), inc1),
        ("push: branches: ['*?'] is refused", branches("*?"), inc1),
        ("push: branches: ['ma[in'] is refused", branches("ma[in"), inc1),
        ("push: branches: ['ma]in'] is refused", branches("ma]in"), inc1),
        ("push: branches: trailing backslash is refused", branches("main\\"), inc1),
        (
            "push: branches: with no value is refused",
            pushed("  push:\n    branches:\n"),
            inc1,
        ),
        (
            "push: branches and branches-ignore is refused",
            pushed("  push:\n    branches: [main]\n    branches-ignore: [x]\n"),
            inc1,
        ),
        ("push: [x] is refused", pushed("  push: [x]\n"), inc1),
        # only a required context counts, and only where pull_request also runs
        (
            "on: push alone",
            repo("on: push\njobs:\n  check:\n    runs-on: x\n"),
            ["ORPHANED"],
        ),
        (
            "unrequired job on push and pull_request",
            repo(_PR.format(job="check").replace(_ON, "on: [push, pull_request]\n"), []),
            ["UNGATED"],
        ),
        (
            "pull_request into another branch",
            pushed("  push:\n", "  pull_request:\n    branches: [develop]\n"),
            ["ORPHANED"],
        ),
        # a called workflow's contexts: the caller's push decides, not the called file's
        (
            "caller on [push, pull_request]",
            repo(
                caller(remote).replace(_ON, "on: [push, pull_request]\n"),
                kind,
                called={remote: conf},
            ),
            dup,
        ),
        (
            "caller on push: [main]; called workflow also on push",
            repo(
                caller(remote),
                kind,
                called={remote: conf.replace("on:\n", "on:\n  push:\n")},
            ),
            [],
        ),
        (
            "local caller on [push, pull_request]",
            repo(
                caller(local).replace(_ON, "on: [push, pull_request]\n"),
                kind,
                more={".github/workflows/k.yml": conf},
            ),
            dup,
        ),
        (
            "caller with an unrequired called job on push",
            repo(
                caller(remote).replace(_ON, "on: [push, pull_request]\n"),
                kind,
                called={remote: conf + extra},
            ),
            ["DUPLICATE", "UNGATED"],
        ),
    ]

    # a second producer in another workflow: its push runs on the pull request's branch (#18)
    def beside(push_wf, wf=None, required=_CHECK):
        return repo(wf or _PR.format(job="check"), required, more={"p.yml": push_wf})

    def push_job(head="check:", body="", on="push"):
        return f"on: {on}\njobs:\n  {head}\n    runs-on: x\n{body}"

    filtered = "\n  push:\n    branches: ['*', '!*']\n"
    disabled = beside(push_job())
    disabled["r"]["workflow_state"]["p.yml"] = "disabled_manually"
    pushed_caller = f"on: push\njobs:\n  kind:\n    uses: {remote}\n"
    cross = [
        ("push job of the same id in another workflow", beside(push_job()), dup),
        (
            "push job named by name: in another workflow",
            beside(push_job("p:", "    name: check\n")),
            dup,
        ),
        (
            "push job with an if: still reports",
            beside(push_job(body="    if: github.ref == 'refs/heads/main'\n")),
            dup,
        ),
        (
            "push with branches-ignore in another workflow",
            beside(push_job(on="\n  push:\n    branches-ignore: [main]\n")),
            dup,
        ),
        (
            "called workflow under push in another workflow",
            repo(
                caller(local),
                kind,
                more={".github/workflows/k.yml": conf, "p.yml": pushed_caller},
                called={remote: conf},
            ),
            dup,
        ),
        (
            "own push and another workflow's push are two findings",
            beside(push_job(), _PR.format(job="check").replace(_ON, "on: [push, pull_request]\n")),
            ["DUPLICATE", "DUPLICATE"],
        ),
        (
            "unrequired context with a push producer elsewhere",
            beside(push_job(), required=[]),
            ["UNGATED"],
        ),
        # negative controls
        (
            "push to the default branch only, in another workflow",
            beside(push_job(on="\n  push:\n    branches: [main]\n")),
            [],
        ),
        (
            "tags-only push in another workflow",
            beside(push_job(on="\n  push:\n    tags: [v*]\n")),
            [],
        ),
        ("push job with a different id", beside(push_job("lint:")), []),
        (
            "push job id matches but name: differs",
            beside(push_job("check:", "    name: lint\n")),
            [],
        ),
        ("disabled push workflow", disabled, []),
        (
            "called workflow under push with other job names",
            repo(
                caller(local),
                kind,
                more={".github/workflows/k.yml": conf, "p.yml": pushed_caller},
                called={remote: called("  lint:\n    runs-on: x\n")},
            ),
            [],
        ),
        ("undecided push filter, different name", beside(push_job("lint:", on=filtered)), []),
        (
            "expression name under a default-only push",
            beside(
                push_job(
                    "p:", "    name: ${{ github.ref_name }}\n", "\n  push:\n    branches: [main]\n"
                )
            ),
            [],
        ),
        # cannot be decided: refused, never passed
        (
            "push job with an expression name is refused",
            beside(push_job("p:", "    name: ${{ github.ref_name }}\n")),
            inc1,
        ),
        (
            "push matrix job is refused",
            beside(push_job(body="    strategy:\n      matrix:\n        v: [1]\n")),
            inc1,
        ),
        ("undecided push filter, same name, is refused", beside(push_job(on=filtered)), inc1),
        (
            "unreadable called workflow under push is refused",
            repo(
                caller(local),
                kind,
                more={".github/workflows/k.yml": conf, "p.yml": pushed_caller},
                called={},
            ),
            inc1,
        ),
    ]

    # a second producer on the pull request itself: pull_request or pull_request_target (#20)
    def target(trigger="  pull_request_target:\n", job="check", body=""):
        return f"on:\n{trigger}jobs:\n  {job}:\n    runs-on: x\n{body}"

    pr_target = target()
    pr_plain = target("  pull_request:\n")

    def state_of(snap, path, state):
        snap["r"]["workflow_state"][path] = state
        return snap

    lint = _CHECK + [{"context": "lint"}]
    inactive_push = state_of(beside(push_job()), "p.yml", "disabled_inactivity")
    pulled_caller = f"on: pull_request\njobs:\n  kind:\n    uses: {remote}\n"
    pr_pair = [
        ("two pull_request workflows", beside(pr_plain), dup),
        ("pull_request and pull_request_target workflows", beside(pr_target), dup),
        (
            "pull_request_target first by path, pull_request second",
            repo(pr_target, more={"x.yml": pr_plain}),
            dup,
        ),
        (
            "pull_request_target job named by name:",
            beside(target(job="p", body="    name: check\n")),
            dup,
        ),
        (
            "one workflow on pull_request and pull_request_target",
            repo(target("  pull_request:\n  pull_request_target:\n")),
            dup,
        ),
        (
            "three workflows give one finding per pair",
            repo(pr_plain, more={"p.yml": pr_plain, "q.yml": pr_target}),
            ["DUPLICATE", "DUPLICATE", "DUPLICATE"],
        ),
        (
            "push and pull_request in another workflow are two producers",
            beside(target("  push:\n  pull_request:\n")),
            ["DUPLICATE", "DUPLICATE", "DUPLICATE"],
        ),
        (
            "called workflow under pull_request in another workflow",
            repo(
                caller(local),
                kind,
                more={".github/workflows/k.yml": conf, "p.yml": pulled_caller},
                called={remote: conf},
            ),
            dup,
        ),
        ("unrequired pull_request_target job", repo(pr_target, []), ["UNGATED"]),
        (
            "pull_request_target with an if:",
            repo(pr_target + "    if: false\n"),
            ["CONDITIONAL"],
        ),
        (
            "pull_request_target types: [labeled]",
            repo(target("  pull_request_target:\n    types: [labeled]\n")),
            ["TRIGGER"],
        ),
        (
            "pull_request_target path-filtered",
            repo(target("  pull_request_target:\n    paths: [a]\n")),
            ["PATH-FILTER"],
        ),
        # with both events, a filter or types: matter only when both have one
        (
            "pull_request path-filtered, pull_request_target not",
            repo(target("  pull_request:\n    paths: [a]\n  pull_request_target:\n")),
            dup,
        ),
        (
            "both events path-filtered",
            repo(
                target("  pull_request:\n    paths: [a]\n  pull_request_target:\n    paths: [a]\n")
            ),
            ["DUPLICATE", "PATH-FILTER"],
        ),
        (
            "pull_request types: [labeled], pull_request_target default",
            repo(target("  pull_request:\n    types: [labeled]\n  pull_request_target:\n")),
            dup,
        ),
        (
            "both events types: [labeled]",
            repo(
                target(
                    "  pull_request:\n    types: [labeled]\n"
                    "  pull_request_target:\n    types: [labeled]\n"
                )
            ),
            ["DUPLICATE", "TRIGGER"],
        ),
        # negative controls
        (
            "pull_request_target into another branch",
            repo(target("  pull_request_target:\n    branches: [develop]\n")),
            ["ORPHANED"],
        ),
        (
            "other pull_request filtered to another base branch",
            beside(target("  pull_request:\n    branches: [develop]\n")),
            [],
        ),
        (
            "other pull_request_target filtered to another base branch",
            beside(target("  pull_request_target:\n    branches-ignore: [main]\n")),
            [],
        ),
        (
            "other pull_request job with a different name",
            beside(target("  pull_request:\n", job="lint"), None, lint),
            [],
        ),
        (
            "other pull_request_target job with a different name",
            beside(target(job="lint"), None, lint),
            [],
        ),
        ("other merge_group job of the same name", beside(target("  merge_group:\n")), []),
        (
            "disabled pull_request workflow",
            state_of(beside(pr_plain), "p.yml", "disabled_manually"),
            [],
        ),
        (
            "disabled_inactivity pull_request_target workflow",
            state_of(beside(pr_target), "p.yml", "disabled_inactivity"),
            [],
        ),
        ("disabled_inactivity push workflow", inactive_push, []),
        # cannot be decided: refused, never passed
        (
            "other pull_request matrix job is refused",
            beside(pr_plain + "    strategy:\n      matrix:\n        v: [1]\n"),
            inc2,
        ),
        (
            "other pull_request filter it cannot read is refused",
            beside(target("  pull_request:\n    branches: ['ma?n']\n")),
            inc2,
        ),
        (
            "other pull_request filter it cannot read, different name",
            beside(target("  pull_request:\n    branches: ['ma?n']\n", job="lint")),
            inc1,
        ),
    ]
    cases = [
        ("clean", repo(_PR.format(job="check")), [], None),
        ("named job is clean", repo(_PR.format(job="j") + "    name: check\n"), [], None),
        ("ungated job", repo(_PR.format(job="check") + extra), ["UNGATED"], None),
        (
            "orphaned context",
            repo(_PR.format(job="check"), _CHECK + [{"context": "gone"}]),
            ["ORPHANED"],
            None,
        ),
        ("tag-only job is not a pr job", repo(tags, []), [], None),
        (
            "required but path-filtered",
            repo(_on("  pull_request:\n    paths: ['a/**']\n")),
            ["PATH-FILTER"],
            None,
        ),
        (
            "required but paths-ignore",
            repo(_on("  pull_request:\n    paths-ignore: ['a/**']\n")),
            ["PATH-FILTER"],
            None,
        ),
        (
            "allowlisted",
            repo(_PR.format(job="check") + extra),
            [],
            {("r", "w.yml", "extra"): "test"},
        ),
        (
            "stale allowlist",
            repo(_PR.format(job="check")),
            ["STALE-ALLOW"],
            {("r", "w.yml", "gone"): "test"},
        ),
        (
            "merge_group only never reports on the PR",
            repo(_on("  merge_group:\n")),
            ["ORPHANED"],
            None,
        ),
        (
            "pull_request_target reports on the PR head",
            repo("on: pull_request_target\njobs:\n  check:\n    runs-on: x\n"),
            [],
            None,
        ),
        (
            "push only does not count",
            repo("on: [push]\njobs:\n  check:\n    runs-on: x\n"),
            ["ORPHANED"],
            None,
        ),
        (
            "types: [labeled]",
            repo(_on("  pull_request:\n    types: [labeled]\n")),
            ["TRIGGER"],
            None,
        ),
        (
            "types with opened and synchronize is clean",
            repo(_on("  pull_request:\n    types: [opened, synchronize, labeled]\n")),
            [],
            None,
        ),
        (
            "branches: [develop] excludes main",
            repo(_on("  pull_request:\n    branches: [develop]\n")),
            ["ORPHANED"],
            None,
        ),
        (
            "branches-ignore: [main]",
            repo(_on("  pull_request:\n    branches-ignore: [main]\n")),
            ["ORPHANED"],
            None,
        ),
        (
            "negated branch pattern",
            repo(_on("  pull_request:\n    branches: ['**', '!main']\n")),
            ["ORPHANED"],
            None,
        ),
        (
            "branches: ['ma*'] includes main",
            repo(_on("  pull_request:\n    branches: ['ma*']\n")),
            [],
            None,
        ),
        (
            "job-level if: is skippable",
            repo(_PR.format(job="check") + "    if: github.event_name == 'push'\n"),
            ["CONDITIONAL"],
            None,
        ),
        (
            "needs a job with an if:",
            repo(
                _PR.format(job="check") + "    needs: build\n"
                "  build:\n    if: github.event_name == 'push'\n    runs-on: x\n",
                _CHECK + [{"context": "build"}],
            ),
            ["CONDITIONAL", "CONDITIONAL"],
            None,
        ),
        (
            "needs an unrequired job",
            repo(_PR.format(job="check") + "    needs: [build]\n  build:\n    runs-on: x\n"),
            ["UNGATED", "CONDITIONAL"],
            None,
        ),
        (
            "needs a required job is clean",
            repo(
                _PR.format(job="check") + "    needs: [build]\n  build:\n    runs-on: x\n",
                _CHECK + [{"context": "build"}],
            ),
            [],
            None,
        ),
        (
            "matrix is not passed",
            repo(_PR.format(job="check") + "    strategy:\n      matrix:\n        v: [1, 2]\n"),
            inc2,
            None,
        ),
        (
            "reusable workflow is not passed",
            repo(
                _PR.format(job="check") + "    uses: kindspec/kindkit/.github/workflows/c.yml@v1\n"
            ),
            inc2,
            None,
        ),
        (
            "expression name is not passed",
            repo(_PR.format(job="j") + "    name: ${{ matrix.v }}\n"),
            inc2,
            None,
        ),
        (
            "context from another app is not passed",
            repo(_PR.format(job="check"), _CHECK + [{"context": "ci/x", "integration_id": 1}]),
            ["INCOMPLETE"],
            None,
        ),
        (
            "unparseable is not passed",
            repo("on: &a [pull_request]\njobs:\n  check:\n    runs-on: x\n"),
            inc2,
            None,
        ),
        (
            "unreadable repository is not passed",
            {"r": {"unreadable": "HTTP 403"}},
            ["INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        ("nothing read is not passed", {}, ["INCOMPLETE"], None),
        ("glob ? is refused", repo(_on("  pull_request:\n    branches: ['ma?n']\n")), inc2, None),
        (
            "tab indentation is refused",
            repo("on: [pull_request]\njobs:\n  check:\n    \truns-on: x\n"),
            inc2,
            None,
        ),
        (
            "flow mapping is refused",
            repo("on: {pull_request: x}\njobs:\n  check:\n    runs-on: x\n"),
            inc2,
            None,
        ),
        (
            "nested flow sequence is refused",
            repo("on: [pull_request, [x]]\njobs:\n  check:\n    runs-on: x\n"),
            inc2,
            None,
        ),
        (
            "unexpected indentation is refused",
            repo(_PR.format(job="check") + "      stray: y\n"),
            inc2,
            None,
        ),
        ("scalar job is refused", repo("on: [pull_request]\njobs:\n  check: x\n"), inc2, None),
        (
            "sequence job is refused",
            repo("on: [pull_request]\njobs:\n  check: [runs-on]\n"),
            inc2,
            None,
        ),
        ("scalar jobs is refused", repo("on: [pull_request]\njobs: x\n"), inc2, None),
        ("top-level sequence is refused", repo("- on: pull_request\n"), inc2, None),
        (
            "job without runs-on or uses is refused",
            repo("on: [pull_request]\njobs:\n  check:\n    steps:\n      - run: x\n"),
            inc2,
            None,
        ),
        (
            "block-scalar name is not passed",
            repo(_PR.format(job="j") + "    name: >-\n      check\n"),
            inc2,
            None,
        ),
        (
            "needs an unknown job",
            repo(_PR.format(job="check") + "    needs: ghost\n"),
            ["CONDITIONAL"],
            None,
        ),
        (
            "needs an unevaluated job",
            repo(
                _PR.format(job="check") + "    needs: b\n  b:\n    runs-on: x\n"
                "    strategy:\n      matrix:\n        v: [1]\n",
                _CHECK + [{"context": "b"}],
            ),
            ["CONDITIONAL", "INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        (
            "disabled workflow produces nothing",
            repo(_PR.format(job="check"), state="disabled_manually"),
            ["ORPHANED"],
            None,
        ),
        (
            "disabled_inactivity workflow produces nothing",
            repo(_PR.format(job="check"), state="disabled_inactivity"),
            ["ORPHANED"],
            None,
        ),
        (
            "workflow with no state is not passed",
            {"r": {**repo(_PR.format(job="check"))["r"], "workflow_state": {}}},
            inc2,
            None,
        ),
        (
            "snapshot without workflow states is not passed",
            {"r": {"workflows": {}, "required": [], "default_branch": "main"}},
            inc2,
            None,
        ),
        (
            "snapshot without a default branch is not passed",
            {"r": {"workflows": {}, "required": []}},
            ["INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        *reusable,
        *((label, snap, want, None) for label, snap, want in duplicate),
        *((label, snap, want, None) for label, snap, want in cross),
        *((label, snap, want, None) for label, snap, want in pr_pair),
    ]
    bad = 0

    def report(label, got, code, want, want_code):
        nonlocal bad
        ok = sorted(got) == sorted(want) and code == want_code
        bad += not ok
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {label}: got {got} exit {code}, want {want} exit {want_code}")

    for label, snap, want, allow in cases:
        got, code = run(snap, allow)
        want_code = 1 if set(want) - {"INCOMPLETE"} else 2 if want else 0  # not via exit_code
        report(label, got, code, want, want_code)

    # the summary counts each called job, not its caller, alongside plain jobs
    snap = repo(
        _PR.format(job="check") + caller(remote).split("jobs:\n")[1],
        _CHECK + kind + [{"context": "kind / b"}],
        called={remote: conf + "  b:\n    runs-on: x\n"},
    )
    f, inc, stats = evaluate(snap, {})
    got = [x.split()[0] for x in f] + ["INCOMPLETE"] * len(inc) + ["?"] * (stats["pr_jobs"] != 3)
    report(f"3 pull_request jobs counted ({stats['pr_jobs']})", got, exit_code(f, inc), [], 0)

    # collection: failures exit 2, never 1 and never a crash
    pub = {"name": "p", "default_branch": "main", "archived": False, "private": False}
    priv = {"name": "q", "default_branch": "main", "archived": False, "private": True}
    forbidden = Unreadable("gh api ... failed: Upgrade to GitHub Pro (HTTP 403)")

    def org(repos, public=None, private=None, **more):
        public = sum(not r["private"] for r in repos) if public is None else public
        base = {
            "orgs/o/repos": repos,
            "orgs/o": {"public_repos": public, "total_private_repos": private},
            "repos/o/p/actions/workflows": {"workflows": []},
            "repos/o/q/actions/workflows": {"workflows": []},
            "repos/o/p/rules/": [],
        }
        return {**base, **more}

    def blob(text):
        return {"content": base64.b64encode(text.encode()).decode()}

    kind_at = "repos/kindspec/kindkit/contents/.github/workflows/kind.yml"
    calls = {
        "repos/o/p/contents/.github/workflows": [
            {"type": "file", "name": "c.yml", "path": ".github/workflows/c.yml"}
        ],
        "repos/o/p/contents/.github/workflows/c.yml": blob(caller(remote)),
        "repos/o/p/actions/workflows": {
            "workflows": [{"path": ".github/workflows/c.yml", "state": "active"}]
        },
        "repos/o/p/rules/": [
            {"type": "required_status_checks", "parameters": {"required_status_checks": kind}}
        ],
    }

    collection = [
        ("unknown org", {"orgs/o/repos": None}, False, ["INCOMPLETE"], 2),
        (
            "branch protection checks are read",
            org(
                [pub],
                private=0,
                **{
                    "repos/o/p/branches/": {
                        "protection": {"required_status_checks": {"checks": [{"context": "bp"}]}}
                    }
                },
            ),
            False,
            ["ORPHANED"],
            1,
        ),
        (
            "private repo without rulesets",
            org([priv], private=1, **{"repos/o/q/rules/": forbidden}),
            False,
            inc2,
            2,
        ),
        (
            "rules endpoint 404 is not passed",
            org([pub], private=0, **{"repos/o/p/rules/": None}),
            False,
            inc2,
            2,
        ),
        (
            "unreadable workflow states are not passed",
            org([pub], private=0, **{"repos/o/p/actions/workflows": None}),
            False,
            inc2,
            2,
        ),
        ("private count unavailable is not passed", org([pub]), False, ["INCOMPLETE"], 2),
        (
            "unlisted private repository is not passed",
            org([pub], private=1),
            False,
            ["INCOMPLETE"],
            2,
        ),
        (
            "unlisted public repository is not passed",
            org([pub], public=2, private=0),
            False,
            ["INCOMPLETE"],
            2,
        ),
        (
            "all listed is clean",
            org([pub, priv], private=1, **{"repos/o/q/rules/": []}),
            False,
            [],
            0,
        ),
        (
            "called workflow is read at the ref it is pinned to",
            org([pub], private=0, **calls, **{f"{kind_at}?ref=abc1": blob(conf)}),
            False,
            [],
            0,
        ),
        (
            "called workflow absent at its ref is not passed",
            org([pub], private=0, **calls, **{f"{kind_at}?ref=main": blob(conf)}),
            False,
            inc2,
            2,
        ),
        (
            "called workflow that cannot be fetched is not passed",
            org([pub], private=0, **calls, **{f"{kind_at}?ref=abc1": forbidden}),
            False,
            inc2,
            2,
        ),
    ]
    for label, responses, public_only, want, want_code in collection:
        got, code, _ = live(responses, public_only)
        report(label, got, code, want, want_code)
    for label, private, want_skipped in (
        ("--public-only counts what it skips", 1, 1),
        ("--public-only says when it cannot count", None, None),
    ):
        got, code, skipped = live(org([pub, priv], private=private), public_only=True)
        report(f"{label} ({skipped})", got + ["?"] * (skipped != want_skipped), code, [], 0)
    global GH
    saved = GH
    try:
        for label, cmd in (
            ("no gh", ["/nonexistent/gh"]),
            (
                "bad token",
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('Bad credentials (HTTP 401)'); sys.exit(1)",
                ],
            ),
        ):
            GH = cmd
            try:
                f, inc, _, _ = run_live("o", False)
            except Exception as e:  # noqa: BLE001
                f, inc = [f"CRASH {type(e).__name__}"], []
            report(label, ["INCOMPLETE"] * len(inc) + f, exit_code(f, inc), ["INCOMPLETE"], 2)
    finally:
        GH = saved
    total = len(cases) + len(collection) + 5
    print(f"selftest: {total - bad} of {total} as expected")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--org", default="kindspec")
    ap.add_argument("--public-only", action="store_true", help="skip private repositories")
    ap.add_argument("--save", metavar="FILE", help="write the collected snapshot as JSON")
    ap.add_argument("--load", metavar="FILE", help="evaluate a saved snapshot, offline")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    skipped = 0
    if args.load:
        with open(args.load) as fh:
            findings, incomplete, stats = evaluate(json.load(fh), ALLOW)
    else:
        findings, incomplete, stats, skipped = run_live(args.org, args.public_only, args.save)
    for line in findings:
        print(line)
    for line in incomplete:
        print(f"INCOMPLETE   {line}")
    if args.public_only and not args.load:
        count = "an unknown number of" if skipped is None else str(skipped)
        print(f"{count} private repositories skipped (--public-only)")
    print(
        f"{stats['repos']} repositories, {stats['workflows']} workflows, "
        f"{stats['pr_jobs']} pull_request jobs, {stats['required']} required checks: "
        f"{len(findings)} finding(s), {len(incomplete)} not evaluated"
    )
    return exit_code(findings, incomplete)


if __name__ == "__main__":
    sys.exit(main())
