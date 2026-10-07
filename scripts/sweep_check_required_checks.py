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
    ("conditional never reported", "skip = _skippable(job_id, jobs, required)", "skip = None"),
    ("job-level if ignored", "    if jobs[job_id][2]:\n", "    if False:\n"),
    ("unrequired need ignored", "        if jobs[n][1] not in required:\n", "        if False:\n"),
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
    ("reusable treated as plain", 'if "uses" in job:', "if False:"),
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
