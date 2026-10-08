# SPDX-License-Identifier: MIT
"""Mutation sweep for check_required_checks.py: its --selftest must catch each mutant.

A mutant is caught when a self-test case reports FAIL, and crashed when the
self-test dies instead; both are red, and they are counted apart.

Each mutant is applied to a copy in a temporary directory; the source is never
edited in place. A pattern that does not match exactly once, or a mutation that
leaves the text unchanged, is BROKEN, never a pass. Exit 0 only when every
mutant is caught.

    python3 scripts/sweep_check_required_checks.py
"""

import hashlib
import pathlib
import subprocess
import sys
import tempfile

TARGET = pathlib.Path(__file__).resolve().parent / "check_required_checks.py"

MUTANTS = [
    (
        "ungated never reported",
        "                if context not in required:\n",
        "                if False:\n",
    ),
    (
        "orphaned never reported",
        "            elif context not in produced:\n",
        "            elif False:\n",
    ),
    ("path filter ignored", "                if filtered:\n", "                if False:\n"),
    ("paths-ignore ignored", '{"paths", "paths-ignore"}', '{"paths"}'),
    ("restrictive types ignored", "                if types:\n", "                if False:\n"),
    ("types check inverted", "not DEFAULT_TYPES <= types", "DEFAULT_TYPES <= types"),
    (
        "conditional never reported",
        "                    if skip:\n",
        "                    if False:\n",
    ),
    ("job-level if ignored", "    if jobs[job_id][2]:\n", "    if False:\n"),
    ("unrequired need ignored", "if any(c not in required for c in contexts):", "if False:"),
    (
        "any pr-ish event counts",
        'if "pull_request" in on:',
        'if {"pull_request", "pull_request_target", "merge_group"} & set(on):',
    ),
    (
        "branches-ignore ignored",
        "        return not any(_glob(str(p)).match(branch) for p in ignore)",
        "        return True",
    ),
    ("negated branch ignored", '        if p.startswith("!"):', "        if False:"),
    ("stale allow ignored", "set(allow) - used", "set()"),
    ("empty org passes", 'if stats["repos"] == 0:', "if False:"),
    ("matrix treated as plain", '"matrix" in job["strategy"]', "False"),
    ("reusable treated as plain", "        if job[5] and not job[4]:\n", "        if False:\n"),
    ("local call not read", "    m = LOCAL_CALL.match(uses)\n", "    m = None\n"),
    ("caller name not prefixed", 'f"{context} / {cname}"', "cname"),
    ("called job if ignored", 'f"{context} / {cname}", has_if,', 'f"{context} / {cname}", False,'),
    ("called job needs ignored", "has_if, needs, None, None)", "has_if, [], None, None)"),
    (
        "caller conditions ignored for called jobs",
        "skip = _skippable(job_id, jobs, required, calls)",
        "skip = None if cid else _skippable(job_id, jobs, required, calls)",
    ),
    (
        "called job conditions ignored",
        "                    elif cid:\n",
        "                    elif False:\n",
    ),
    ("nested call accepted", "            if nested:\n", "            if False:\n"),
    (
        "unread called job accepted",
        "            if unresolved:\n                return None",
        "            if False:\n                return None",
    ),
    ("no workflow_call accepted", 'if "workflow_call" not in _events(workflow):', "if False:"),
    ("unreadable call accepted", "if not isinstance(text, str):", "if False:"),
    (
        "call missing from snapshot accepted",
        '        if text is None:\n            return None, f"calls {uses}, which the snapshot',
        '        if False:\n            return None, f"calls {uses}, which the snapshot',
    ),
    ("unrecognised uses accepted", "elif REMOTE_CALL.match(uses):", "elif True:"),
    (
        "unparseable call accepted",
        'return None, f"calls {uses}, which cannot be read: {e}"',
        "return {}, None",
    ),
    ("call fetched without its ref", "?ref={urllib.parse.quote(ref, safe='')}", ""),
    ("calls not collected", "called[uses] = _fetch_call(uses, api)", "pass"),
    (
        "needed caller's called contexts ignored",
        "contexts = [c[1] for c in inner.values()] if n in calls else [jobs[n][1]]",
        "contexts = [jobs[n][1]]",
    ),
    (
        "needed caller's called conditions ignored",
        "            why = why or _skippable(cid, inner, required, {})\n",
        "            pass\n",
    ),
    (
        "call looked up without its ref",
        '        text = (data.get("called") or {}).get(uses)\n',
        (
            '        text = next((v for k, v in (data.get("called") or {}).items()'
            ' if k.split("@")[0] == uses.split("@")[0]), None)\n'
        ),
    ),
    (
        "path filter ignored for called jobs",
        "                    if filtered:\n",
        "                    if filtered and not cid:\n",
    ),
    (
        "types ignored for called jobs",
        "                    if types:\n",
        "                    if types and not cid:\n",
    ),
    (
        "called jobs not counted",
        '                    stats["pr_jobs"] += 1\n                    produced.add(context)\n',
        '                    stats["pr_jobs"] += 0\n                    produced.add(context)\n',
    ),
    (
        "uses with runs-on or steps accepted",
        '        if "uses" in job and {"runs-on", "steps"} & set(job):\n',
        "        if False:\n",
    ),
    ("expression name accepted", 'elif "${{" in context:', "elif False:"),
    ("other app accepted", "if app not in (None, ACTIONS_APP_ID):", "if False:"),
    ("blind orphan reported as finding", "elif context not in produced and blind:", "elif False:"),
    ("job name ignored", 'str(job.get("name", job_id))', "str(job_id)"),
    ("anchors accepted", 'if v[:1] in "&*!"', "if False"),
    (
        "branch protection ignored",
        'required.append({"context": c["context"]',
        'None and required.append({"context": c["context"]',
    ),
    (
        "unreadable repo skipped",
        '        if data.get("unreadable"):\n            incomplete',
        '        if data.get("unreadable"):\n            continue\n            incomplete',
    ),
    ("unknown org crashes", "    if not isinstance(repos, list):\n", "    if False:\n"),
    ("missing gh crashes", "    except OSError as e:\n", "    except ZeroDivisionError as e:\n"),
    (
        "public-only does not skip",
        '        if public_only and repo["private"]:\n',
        "        if False:\n",
    ),
    ("exit always 0", "    return 1 if findings else 2 if incomplete else 0", "    return 0"),
    ("incomplete exits 0", "else 2 if incomplete else 0", "else 0"),
    ("glob ?+[] accepted", '    if re.search(r"[?+\\[\\]]", pattern):\n', "    if False:\n"),
    (
        "tab indentation accepted",
        '        if "\\t" in line[: len(line) - len(line.lstrip())]:\n',
        "        if False:\n",
    ),
    ("flow mapping accepted", '        if v.replace(" ", "") != "{}":\n', "        if False:\n"),
    ("nested flow sequence accepted", 'or "[" in v[1:-1] or "{" in v[1:-1]', ""),
    ("unexpected indentation accepted", "    if i != len(lines):\n", "    if False:\n"),
    ("needs unknown job accepted", "        if n not in jobs:\n", "        if False:\n"),
    ("needs unevaluated job accepted", "        if jobs[n][4]:\n", "        if False:\n"),
    ("rules 404 accepted", "            if rules is None:\n", "            if False:\n"),
    (
        "workflow not a mapping accepted",
        "    if not isinstance(workflow, dict):\n",
        "    if False:\n",
    ),
    (
        "jobs not a mapping accepted",
        "    if not isinstance(jobs, dict):\n        raise",
        "    if False:\n        raise",
    ),
    (
        "job not a mapping accepted",
        "        if not isinstance(job, dict):\n",
        "        if False:\n",
    ),
    (
        "job without runs-on or uses accepted",
        '        if "runs-on" not in job and "uses" not in job:\n',
        "        if False:\n",
    ),
    ("block-scalar name accepted", '        elif context == "<block>":\n', "        elif False:\n"),
    ("disabled workflow counted", '            if state != "active":\n', "            if False:\n"),
    (
        "missing workflow state accepted",
        "            if state is None:\n",
        "            if False:\n",
    ),
    (
        "snapshot without states accepted",
        '        if "workflow_state" not in data:\n',
        "        if False:\n",
    ),
    (
        "unreadable states accepted",
        "            if not isinstance(runs, dict):\n",
        "            if False:\n",
    ),
    (
        "unlisted public accepted",
        "if public is None or listed_public < public:",
        "if public is None:",
    ),
    ("unknown private count accepted", "    elif private is None:\n", "    elif False:\n"),
    ("unlisted private accepted", "    elif listed_private < private:\n", "    elif False:\n"),
    (
        "public-only claims a count",
        "skipped = None if private is None else",
        "skipped = 0 if private is None else",
    ),
    # DUPLICATE: a required context's workflow also runs on push to other branches
    (
        "duplicate never reported",
        "                    if pushed:\n",
        "                    if False:\n",
    ),
    (
        "duplicate ignored for called jobs",
        "                    if pushed:\n",
        "                    if pushed and not cid:\n",
    ),
    (
        "undecided push accepted",
        "                    elif unknown:\n",
        "                    elif False:\n",
    ),
    ("unfiltered push ignored", 'return "push has no branch filter"', "return None"),
    ("null push ignored", 'if "push" not in on:', 'if on.get("push") is None:'),
    (
        "unreadable push accepted",
        '    if not isinstance(config, dict):\n        raise Unsupported(f"unreadable push',
        '    if False:\n        raise Unsupported(f"unreadable push',
    ),
    ("tags-only push counted", "return None  # tags only", 'return "tags"'),
    ("both branch filters accepted", 'if {"branches", "branches-ignore"} <= refs:', "if False:"),
    ("empty push filter accepted", "if value is None or isinstance(value, dict):", "if False:"),
    (
        "ignore-all not recognised",
        r'if any(re.fullmatch(r"\**\*\*\**", p) for p in ignore):',
        "if False:",
    ),
    ("ignored branch is a witness", "if not any(r.match(name) for r in regexes):", "if True:"),
    (
        "undecided branches-ignore passed",
        '        raise Unsupported(f"push branches-ignore {ignore}: cannot tell what it admits")',
        "        return None",
    ),
    (
        "undecided branches passed",
        '    raise Unsupported(f"push branches {patterns}: cannot tell what they admit")',
        "    return None",
    ),
    ("no generic witnesses", 'others = ["x", "x/x",', 'others = [] and ["x", "x/x",'),
    ("pattern samples not tried", "            others += samples\n", "            pass\n"),
    ("unbounded pattern settled", "settled &= finite or", "settled &= True or"),
    (
        "later '!**' not credited",
        r'any(re.fullmatch(r"!\**\*\*\**", q) for q in patterns[n:])',
        "False",
    ),
    ("earlier '!**' credited", "for q in patterns[n:])", "for q in patterns)"),
    (
        "push negation ignored",
        "                runs = not negated\n",
        "                runs = True\n",
    ),
    ("default branch is a witness", "if runs and name != branch and", "if runs and"),
    ("impossible name is a witness", "and _branch_name(name):", ":"),
    ("finite pattern not enumerated", "all(a[2] for a in atoms) and", "False and"),
    ("sample cap ignored", " and len(samples) <= SAMPLES", ""),
    ("sample cap off by one", "SAMPLES + 1)", "SAMPLES)"),
    ("* crosses '/'", '("[^/]*", ["", "x"]', '(".*", ["", "x"]'),
    ("? matches one, not zero or one", 'f"(?:{r})?"', 'f"(?:{r})"'),
    ("? never sampled empty", '["", *s], finite', "s, finite"),
    ("+ matches only one", 'f"(?:{r})+"', 'f"(?:{r})"'),
    ("+ taken as finite", "*(x + x for x in s)], False", "*(x + x for x in s)], True"),
    ("? or + after nothing accepted", "if not atoms or not atoms[-1][3]:", "if False:"),
    (
        "range not expanded",
        "chars |= {chr(n) for n in range(ord(lo), ord(hi) + 1)}",
        "chars |= {lo, hi}",
    ),
    ("reversed range accepted", "if lo > hi or not any(", "if False or not any("),
    (
        "mixed range accepted",
        "                if lo > hi or not any(\n",
        "                if lo > hi or False and not any(\n",
    ),
    (
        "set body unchecked",
        'if end < 0 or not re.fullmatch(r"(?:[A-Za-z0-9](?:-[A-Za-z0-9])?)+", body):',
        "if end < 0:",
    ),
    ("stray ] accepted", '        elif c == "]":\n', "        elif False:\n"),
    ("backslash not an escape", '            if c == "\\\\":\n', "            if False:\n"),
    (
        "trailing backslash accepted",
        "                if i == len(pattern):\n",
        "                if False:\n",
    ),
]


def main():
    src = TARGET.read_text()
    digest = hashlib.sha256(src.encode()).hexdigest()
    counts = {"caught": 0, "crashed": 0, "SURVIVED": 0, "BROKEN": 0}
    with tempfile.TemporaryDirectory() as tmp:
        copy = pathlib.Path(tmp) / TARGET.name
        for label, old, new in MUTANTS:
            if src.count(old) != 1:
                verdict = "BROKEN"
            else:
                mutated = src.replace(old, new)
                copy.write_text(mutated)
                if hashlib.sha256(copy.read_bytes()).hexdigest() == digest:
                    verdict = "BROKEN"
                else:
                    r = subprocess.run(
                        [sys.executable, "-I", str(copy), "--selftest"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    verdict = (
                        "SURVIVED"
                        if r.returncode == 0
                        else "caught"
                        if "\nFAIL " in "\n" + r.stdout
                        else "crashed"
                    )
            counts[verdict] += 1
            print(f"{verdict:8} {label}")
    assert hashlib.sha256(TARGET.read_bytes()).hexdigest() == digest, "target changed"
    print(
        f"{len(MUTANTS)} mutants: {counts['caught']} caught, {counts['crashed']} crashed "
        f"the self-test, {counts['SURVIVED']} survived, {counts['BROKEN']} broken"
    )
    return 0 if counts["caught"] + counts["crashed"] == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
