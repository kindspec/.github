# SPDX-License-Identifier: MIT
"""Compare each repository's workflow jobs against its required status checks.

Adding a workflow to a repository does not add it to the ruleset, so a suite can
run on every pull request and gate nothing (kindspec/.github#3). This fails when:

  UNGATED      a job that runs on pull requests to the default branch is not a
               required check
  ORPHANED     a required check is a context no such job produces. A job that
               runs only on merge_group, pull_request_target (its check runs
               attach to the base commit), push, on pull requests to other
               branches, or in a workflow that is not `active` does not count:
               the context never reports on the PR head
  TRIGGER      a required job's pull_request `types:` omit opened or synchronize,
               so it does not report on every pull request head
  CONDITIONAL  a required job can be skipped, and GitHub reports a skipped job as
               success: it has a job-level `if:`, or something in its `needs:`
               chain has one or is not itself required. When the skipped job calls
               a reusable workflow, its '<caller> / <called>' contexts never
               report at all, and the merge waits on them instead
  PATH-FILTER  a required job is path-filtered, so it never reports on an
               unrelated pull request and blocks it forever (AGENTS.md 3.2)
  STALE-ALLOW  an ALLOW entry matches no job any more

Exit 0 clean, 1 on any finding, 2 when something could not be evaluated: no
repositories read; an API or authentication failure; fewer repositories listed
than the org reports, or a private count this token cannot read; a repository
whose rules or workflow states cannot be read (rulesets on a private repository
need a paid plan); a workflow the parser cannot read or GitHub would reject
(a job with neither runs-on nor uses, or uses with runs-on or steps, a
non-mapping job); or a matrix,
expression- or block-named job whose context names this script does not expand.
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


def _glob(pattern):
    if re.search(r"[?+\[\]]", pattern):
        raise Unsupported(f"branch filter pattern {pattern!r}")
    parts = (re.escape(p).replace(r"\*", "[^/]*") for p in pattern.split("**"))
    return re.compile(".*".join(parts) + r"\Z")


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


def pr_trigger(workflow, branch):
    """(how the workflow reaches a PR into branch, path-filtered, restricted types, why not)."""
    on = _events(workflow)
    if "pull_request" in on:
        config = on["pull_request"]
        if _branch_runs(config, branch):
            config = config if isinstance(config, dict) else {}
            filtered = bool({"paths", "paths-ignore"} & set(config))
            types = config.get("types")
            if types is not None:
                types = set(map(str, types if isinstance(types, list) else [types]))
            restricted = types is not None and not DEFAULT_TYPES <= types
            return True, filtered, sorted(types) if restricted else None, None
        why = f"pull_request excludes '{branch}'"
    else:
        others = [e for e in ("merge_group", "pull_request_target", "push") if e in on]
        why = "only " + ", ".join(others) if others else None
    return False, False, None, why


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
        for path, text in sorted(data["workflows"].items()):
            stats["workflows"] += 1
            state = data["workflow_state"].get(path)
            if state is None:
                incomplete.append(f"{repo}: {path}: not evaluated: no workflow state")
                blind = True
                continue
            try:
                workflow = parse_yaml(text)
                runs, filtered, types, why = pr_trigger(workflow, branch)
                jobs = {j[0]: j for j in jobs_of(workflow)}
            except Unsupported as e:
                incomplete.append(f"{repo}: {path}: not evaluated: {e}")
                blind = True
                continue
            if state != "active":
                runs, why = False, f"workflow is {state}"
            if not runs:
                for _, context, *_ in jobs.values():
                    if why:
                        elsewhere.setdefault(context, why)
                continue
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

_PR = "on: [push, pull_request]\njobs:\n  {job}:\n    runs-on: x\n"
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
        return f"on: [push, pull_request]\njobs:\n  kind:\n{more}    uses: {uses}\n"

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
            "pull_request_target attaches to the base commit",
            repo("on: pull_request_target\njobs:\n  check:\n    runs-on: x\n"),
            ["ORPHANED"],
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
