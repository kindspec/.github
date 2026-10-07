# SPDX-License-Identifier: MIT
"""Compare each repository's workflow jobs against its required status checks.

Adding a workflow to a repository does not add it to the ruleset, so a suite can
run on every pull request and gate nothing (kindspec/.github#3). This fails when:

  UNGATED      a job that runs on pull_request is not a required check
  ORPHANED     a required check is a context no workflow job produces
  PATH-FILTER  a required job is path-filtered, so it never reports on an
               unrelated pull request and blocks it forever (AGENTS.md 3.2)
  STALE-ALLOW  an ALLOW entry matches no job any more

Exit 0 clean, 1 on any finding, 2 when something could not be evaluated
(no repositories read, an unparseable workflow, a matrix or reusable-workflow
job whose context names this script does not expand). A run that could not
look must not report a pass.

Reads only public data: the org's public repositories, their workflow files on
the default branch, and the rules that apply to that branch
(GET /repos/{o}/{r}/rules/branches/{b}). Uses the `gh` CLI for the calls.

    python3 scripts/check_required_checks.py [--org kindspec]
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

# Jobs that run on pull_request but deliberately gate nothing, as
# (repo, workflow path, job id): reason. Jobs that never run on a pull request
# (rowspec's release.yml: gate, build, publish run on v* tags) are excluded by
# their triggers and need no entry here.
ALLOW = {}

PR_EVENTS = ("pull_request", "pull_request_target", "merge_group")
ACTIONS_APP_ID = 15368  # GitHub Actions; a context from another app is not a workflow job


class Unsupported(Exception):
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
    if i < len(lines) and lines[i][0] > indent:
        raise Unsupported(f"unexpected indentation at {lines[i][1]!r}")
    return mapping, i


def parse_yaml(text):
    lines = _lines(text)
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise Unsupported(f"stopped at {lines[i][1]!r}")
    return value


# --- evaluation ---


def pr_jobs(workflow):
    """Yield (job id, context, path-filtered, unresolved reason) for PR-triggered jobs."""
    on = workflow.get("on")
    if isinstance(on, str):
        on = [on]
    if isinstance(on, list):
        on = {e: None for e in on}
    if not isinstance(on, dict):
        raise Unsupported(f"unreadable 'on': {on!r}")
    events = [e for e in PR_EVENTS if e in on]
    if not events:
        return
    filtered = any(
        isinstance(on[e], dict) and ({"paths", "paths-ignore"} & set(on[e])) for e in events
    )
    for job_id, job in (workflow.get("jobs") or {}).items():
        job = job or {}
        context = str(job.get("name", job_id))
        unresolved = None
        if "uses" in job:
            unresolved = "calls a reusable workflow; contexts are '<caller> / <called job>'"
        elif isinstance(job.get("strategy"), dict) and "matrix" in job["strategy"]:
            unresolved = "matrix job; contexts are expanded per combination"
        elif "${{" in context:
            unresolved = "name is an expression"
        yield job_id, context, filtered, unresolved


def evaluate(snapshot, allow):
    findings, incomplete, used = [], [], set()
    stats = {"repos": 0, "workflows": 0, "pr_jobs": 0, "required": 0}
    for repo, data in sorted(snapshot.items()):
        stats["repos"] += 1
        required = {}
        for c in data["required"]:
            required.setdefault(c["context"], c.get("integration_id"))
        stats["required"] += len(required)
        produced, blind = set(), False
        for path, text in sorted(data["workflows"].items()):
            stats["workflows"] += 1
            try:
                jobs = list(pr_jobs(parse_yaml(text)))
            except Unsupported as e:
                incomplete.append(f"{repo}: {path}: not evaluated: {e}")
                blind = True
                continue
            for job_id, context, filtered, unresolved in jobs:
                stats["pr_jobs"] += 1
                where = f"{repo}: {path}: job '{job_id}'"
                if (repo, path, job_id) in allow:
                    used.add((repo, path, job_id))
                    continue
                if unresolved:
                    incomplete.append(f"{where}: not evaluated: {unresolved}")
                    blind = True
                    continue
                produced.add(context)
                if context not in required:
                    findings.append(
                        f"UNGATED      {where} runs on pull_request; "
                        f"'{context}' is not a required check"
                    )
                elif filtered:
                    findings.append(
                        f"PATH-FILTER  {where} is required but its pull_request "
                        "trigger is path-filtered"
                    )
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
                findings.append(
                    f"ORPHANED     {repo}: required check '{context}' is produced by "
                    "no pull_request job — every pull request waits on it forever"
                )
    for key in sorted(set(allow) - used):
        findings.append(f"STALE-ALLOW  {key} matches no pull_request job")
    if stats["repos"] == 0:
        incomplete.append("no repositories were read")
    return findings, incomplete, stats


def exit_code(findings, incomplete):
    return 1 if findings else 2 if incomplete else 0


# --- collection ---


def gh(path):
    r = subprocess.run(
        ["gh", "api", "--paginate", path], capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        if "HTTP 404" in r.stderr:
            return None
        sys.exit(f"gh api {path} failed: {r.stderr.strip()}")
    # --paginate concatenates JSON arrays as ][
    return json.loads(re.sub(r"\]\s*\[", ",", r.stdout) if r.stdout.startswith("[") else r.stdout)


def collect(org):
    snapshot = {}
    for repo in gh(f"orgs/{org}/repos?type=public&per_page=100"):
        if repo["archived"] or repo["private"]:
            continue
        name, branch = repo["name"], repo["default_branch"]
        workflows = {}
        for entry in gh(f"repos/{org}/{name}/contents/.github/workflows?ref={branch}") or []:
            if entry["type"] == "file" and entry["name"].endswith((".yml", ".yaml")):
                blob = gh(f"repos/{org}/{name}/contents/{entry['path']}?ref={branch}")
                workflows[entry["path"]] = base64.b64decode(blob["content"]).decode()
        required = []
        for rule in gh(f"repos/{org}/{name}/rules/branches/{branch}") or []:
            if rule["type"] == "required_status_checks":
                required += rule["parameters"]["required_status_checks"]
        protection = (gh(f"repos/{org}/{name}/branches/{branch}") or {}).get("protection", {})
        for c in protection.get("required_status_checks", {}).get("checks", []):
            required.append({"context": c["context"], "integration_id": c.get("app_id")})
        snapshot[name] = {"workflows": workflows, "required": required}
    return snapshot


# --- self-test: every finding and every refusal must be seen to fire ---

_PR = "on: [push, pull_request]\njobs:\n  {job}:\n    runs-on: x\n"
_CHECK = [{"context": "check", "integration_id": ACTIONS_APP_ID}]


def selftest():
    def run(snapshot, allow=None):
        f, inc, _ = evaluate(snapshot, allow or {})
        return [x.split()[0] for x in f] + ["INCOMPLETE"] * len(inc), exit_code(f, inc)

    def repo(wf, required=_CHECK):
        return {"r": {"workflows": {"w.yml": wf}, "required": required}}

    tags = (
        "on:\n  push:\n    tags: ['v*']\njobs:\n  gate:\n    steps:\n      - run: |\n          x\n"
    )
    cases = [
        ("clean", repo(_PR.format(job="check")), [], None),
        ("named job is clean", repo(_PR.format(job="j") + "    name: check\n"), [], None),
        (
            "ungated job",
            repo(_PR.format(job="check") + "  extra:\n    runs-on: x\n"),
            ["UNGATED"],
            None,
        ),
        (
            "orphaned context",
            repo(_PR.format(job="check"), _CHECK + [{"context": "gone"}]),
            ["ORPHANED"],
            None,
        ),
        ("tag-only job is not a pr job", repo(tags, []), [], None),
        (
            "required but path-filtered",
            repo("on:\n  pull_request:\n    paths: ['a/**']\njobs:\n  check:\n    runs-on: x\n"),
            ["PATH-FILTER"],
            None,
        ),
        (
            "allowlisted",
            repo(_PR.format(job="check") + "  extra:\n    runs-on: x\n"),
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
            "matrix is not passed",
            repo(_PR.format(job="check") + "    strategy:\n      matrix:\n        v: [1, 2]\n"),
            ["INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        (
            "reusable workflow is not passed",
            repo(
                _PR.format(job="check") + "    uses: kindspec/kindkit/.github/workflows/c.yml@v1\n"
            ),
            ["INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        (
            "unparseable is not passed",
            repo("on: &a [pull_request]\n"),
            ["INCOMPLETE", "INCOMPLETE"],
            None,
        ),
        ("nothing read is not passed", {}, ["INCOMPLETE"], None),
    ]
    bad = 0
    for label, snap, want, allow in cases:
        got, code = run(snap, allow)
        want_code = 1 if set(want) - {"INCOMPLETE"} else 2 if want else 0  # not via exit_code
        ok = sorted(got) == sorted(want) and code == want_code
        bad += not ok
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {label}: got {got} exit {code}, want {want} exit {want_code}")
    print(f"selftest: {len(cases) - bad} of {len(cases)} as expected")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--org", default="kindspec")
    ap.add_argument("--save", metavar="FILE", help="write the collected snapshot as JSON")
    ap.add_argument("--load", metavar="FILE", help="evaluate a saved snapshot, offline")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.load:
        with open(args.load) as fh:
            snapshot = json.load(fh)
    else:
        snapshot = collect(args.org)
    if args.save:
        with open(args.save, "w") as fh:
            json.dump(snapshot, fh, indent=1, sort_keys=True)
    findings, incomplete, stats = evaluate(snapshot, ALLOW)
    for line in findings:
        print(line)
    for line in incomplete:
        print(f"INCOMPLETE   {line}")
    print(
        f"{stats['repos']} repositories, {stats['workflows']} workflows, "
        f"{stats['pr_jobs']} pull_request jobs, {stats['required']} required checks: "
        f"{len(findings)} finding(s), {len(incomplete)} not evaluated"
    )
    return exit_code(findings, incomplete)


if __name__ == "__main__":
    sys.exit(main())
