# State of play

Current as of **2026-10-07**. Read `AGENTS.md` first — it is the contract. This
file is where the work actually stands, what comes next, and the traps that have
already cost time.

Every figure here names the command that produces it. Where a figure cannot be
reproduced from this checkout alone, that is said.

---

## 1. Where each repository stands

### rowspec — draft 0 released, now on kindkit

    410 conformance cases          find conformance/cases -name expect.json | wc -l
    0 failures, reference impl     just conform
    0 failures, second impl        just conform-alt
    74 killed, 0 survived          just mutants
    2 equivalent, 0 stale, 0 broken
    52 passed, 1 skipped           just test   (skip is openpyxl absent)
    294 files clean                just check

**All of these reproduce on 2026-10-06.** They were produced by calling the
`.venv` directly rather than through `just`, because a sandboxed session cannot
run `uv` — see §3. The equivalents:

    ./.venv/bin/python conformance/run_cases.py
    ./.venv/bin/python conformance/run_cases.py rowspec_alt.table
    ./.venv/bin/python conformance/mutants.py
    ./.venv/bin/python -m pytest -q
    ./.venv/bin/ruff format --check . && ./.venv/bin/ruff check .

**rowspec's gate is safe to kill; kindkit's is not.** rowspec writes its mutants
to `conformance/mutant_impl.py`, which is gitignored, and never edits
`reference/rowspec/table.py`, so an interrupted run leaves the tree clean —
confirmed after a kill. **kindkit's gate is the opposite**: `tools/mutation_gate.py`
opens each target in place and restores in a `finally`, and its targets are nine
tracked files spread across `kindkit/`, `tools/`, `case-tree/` and `tests/`. A
completed run is clean; a killed one leaves a mutated tracked file. Run it in a
throwaway clone, and if you do kill one, **`git status` is the list** — do not
restore from a list written down here, which is exactly how two of the nine got
missed when this paragraph was first written.

`v0.1.0` is tagged, on PyPI, and ships a GitHub Action. The suite, the mutation
gate and the case-tree convention now come from kindkit; what stayed is
everything kindkit cannot be told — what a `parse` case means, what `canon`
asserts, how merge sides are filed.

Two numbers to carry correctly: **76 mutants are 74 distinct mutations**, because
two `(old, new)` pairs appear twice, so `74 killed` is 72 distinct kills (#48).
The second implementation (`reference/rowspec_alt/`) is the load-bearing one —
written from `SPEC.md` alone, run against the same fixture tree in CI, and right
on the last three questions where the two disagreed.

### kindkit — complete, and proven against a real consumer

    73 mutations, 73 caught, 0 survived, 0 broken    just mutants
    109 passed                                        just test   (1 skips without node)
    20 files clean                                    just check
    6 cases in its own kv tree                        just cases

All of these reproduce on 2026-10-06, run from `.venv` (see §3 — `uv sync`
creates it; it is not committed) rather than through
`just`, by the same substitution as rowspec's.

**96** test functions across **five** files collect as 109: 92 plain, three
functions over three parameters each, and one over four layout entries in two
directions. `grep -c '^def test_'` says 97 across six, and is wrong twice —
`tests/kvkind.py` is the toy kind and defines none, and the 97th match is inside
a triple-quoted `PROBE_TEST` string in `tests/test_mutation_gate.py`. Count with
`ast`, not `grep`; from 97 the parametrisation arithmetic does not close.

The case-tree validator was also run against rowspec's tree in kindkit PR #6,
giving 429 manifests over both repositories with zero invalid and no fixture
modified — 410 plus 13 reserved plus these 6. That figure needs both checkouts.
Note #6 is a pull request; kindkit has no issue #6.

Three pieces: the tree-driven runner, the case-tree convention under CC0, and the
mutation gate a kind runs against its own implementation. rowspec adopting it
kept every number identical and the same killing cases for all 76 mutants, which
is the only evidence that the abstraction is real rather than fitted.

**The gate is Python-only** — `tokenize`, `ast`, `compile`. A kind whose
reference implementation is not Python gets the runner and not the gate.

### blockspec — pre-registration frozen, harness validated, no verdict

    SELECTION-GUARD SELFTEST: PASS      python3 spike/harness/prose_merge.py --selftest-selection
    SELFTEST: PASS                      python3 spike/harness/check_control_gate.py --selftest
    PLANTED-CASE GATE: PASS             python3 spike/harness/prose_merge.py --plant --d8-dir <research>/experiments/D8-identity

Verified green on 2026-10-06. The harness is **pure stdlib, run with `python3`
directly** — no `uv`, no justfile, so it works where the other two repos need a
toolchain.

`spike/PRE-REGISTRATION.md` is binding. **§3, §4 and §6 cannot be amended**, only
superseded by a new pre-registration that says why. §1, §2, §5 and §7 record
evidence and method and may be corrected, with every change logged in §8.

85 candidate cases exist, **every one `tier: UNASSIGNED`**. §4.1 forbids whoever
has seen the frequencies from assigning tiers, so tiering is a separate job for
someone who has not.

### research — the evidence base, reproducible

Not a specification. It is the design record the three briefs cite, published so
those citations resolve. `anchor_eval*` and `e4_uniqueness` output are committed;
§3.1–3.3 can be reproduced.

**The corpora are not in the repository.** `CORPORA.md` names each one with its
source and the pins §3 records. A fresh machine has to clone them; see §3 below.

### nodespec — stub, zero work

Two commits: the stub, and a pointer at the org contract. No specification, no
suite, no implementation. Its brief names three concrete
`.canvas` referential-integrity holes — an override for a deleted node, an edge
to a renamed node, and two branches adding different nodes with the same name —
and calls the third the most likely home of a genuine silent-wrong merge.

### .github — the org contract and this file

---

## 2. What comes next

**blockspec is trending toward "do not build this," and that is a deliverable.**
D8 records zero typed-prose silent-wrongs under the hardened policy across five
arms. The spike retracted its own central claim — that the defect needs both
merge legs to act — and the retraction makes D8 *stronger* evidence against,
because the shape turns out to be single-leg reachable and D8's arms would have
caught it. Concurrent edits to the same prose file are roughly 1% of the editing
these projects do: 195 accepted cases against 19,337 single-side pairs.

§6 commits both outcomes as deliverables. A published finding that prose does not
earn a format is the likelier draft 0, and it is a result rather than a failure.

In order:

1. **blockspec#2 — run the duplicate-heavy arm.** The corpora are named and
   pinned in `spike/PRE-REGISTRATION.md` §5.1. Ranked by evaluable
   human-authored cases: `kubernetes/website` is the largest arm at roughly 800
   — an **upper** estimate extrapolated from the most recent 400 of 23,473
   merges, so enumerate before quoting it; `cncf/toc` the cleanest at 71 with no
   bot involvement at all; `github/site-policy` a supporting arm at **21 to 25**
   and the only legal-text coverage. Read §5.1 for why that last one is a range
   and not a number. Nothing blocks this.
2. **Tier the 85 candidates, blind.** Needs someone who has not seen the
   frequencies, per §4.1.
3. **blockspec#3 and #4 — the adjudications.** djot versus markdown, and what a
   block is. Both are non-empirical, so §4 of the contract applies: two
   independent arguments from the same evidence, and the adjudication written
   into the repository with its reversal cost.
4. **blockspec#5 — author the case tree before any implementation exists.** The
   §0 decision, and the one discipline rowspec had to retrofit.
5. **kindkit#4 — the reusable CI workflow.** The last v0 item.
6. **nodespec's existential spike**, if blockspec resolves negative. Its brief
   argues the rowspec thesis does not transfer to canvases at all, and that a
   finding of "do not build this" is a legitimate outcome there too.

Twenty-eight issues are open, each with acceptance criteria and a red-before-green
requirement. The ones that touch a gate are `rowspec#39`, `#40`, `#43`, `#48`,
`#49`, `#47` and `kindkit#3`, `#4`, `#8` through `#12` — check the repos' own gate labels rather than trusting this list. `rowspec#44` and `#45` were also
gate defects and are **closed** — the kindkit adoption fixed both.

---

## 3. Setting up on a fresh machine

**Toolchain.** `git`, `just`, `python3` 3.11+, `uv` for rowspec and kindkit,
`ruff` and `pytest` through `uv`, and `pre-commit` — both repositories carry a
`.pre-commit-config.yaml` and all work lands by PR. A real `git` binary is a hard
dependency of every conformance suite, because the central claim is about what
stock git does.

**The three blockspec commands run from `blockspec/`**, and `uv sync` needs
network reach to `github.com` — `rowspec/pyproject.toml` has `kindkit` as a git
dependency in its dev group, so an offline sync fails there.

**First command in rowspec and kindkit is `uv sync`** (or `just setup`, which is
that one line). It creates `.venv`, which is **gitignored and not committed** —
every command in §1 calls `./.venv/bin/...` and none of them work until it
exists. Run it somewhere `~/.cache/uv` is writable; see the sandbox note at the
end of this section for why that is not always where you are.

**`node` is required by kindkit's test suite**, not optionally: the case-tree
validator translates Python regex semantics to ECMA-262 and the differential test
checks the translation against a real engine. Without `node` on `PATH` that test
skips, and a mutation exists specifically so a skip fails the gate rather than
passing quietly. Nothing else needs it.

**Corpora.** They live outside the repositories and are gitignored. **Clone the
pins in `research/design-findings/D8-identity.md` §3. They produce all four
committed artifacts, byte for byte.**

| corpus | pin | source |
|---|---|---|
| `rust-book` | `1500248d8f230566e4ec9f27fcbb8fe9e2898ab1` | `github.com/rust-lang/book` |
| `obsidian-help` | `327a782e90481268361b5ccccdb0c224b2b13fe6` | `github.com/obsidianmd/obsidian-help` |
| `cmspec` | `3da939428d80f146f270cd1765e4ba462e96bb1b` | `github.com/commonmark/commonmark-spec` |

Verified: `anchor_eval3.py` is byte-identical to `results-anchor3.txt` at these
trees, and `e4_uniqueness.py` at 20, 40 and 120 to `results-e4.txt`.

**`blockspec/spike/harness/corpora.json` pins different commits on purpose, and
they are not an alternative set to reproduce research with.** It pins
`obsidian-help` at `a3985b58` and `rust-book` at `917544888a55` to reconstruct
an *earlier, uncommitted* pass — chosen by matching the commit counts in D8 §1's
header, which describe that earlier clone. Its control arm therefore prints
`anchors=384` where `results-anchor3.txt` prints `343`, and both are right about
their own tree. D8 §3.2 states this directly: *"The 384 line belongs to
`a3985b58` alone."* Use `a3985b58` only when running blockspec's control arm.

**Name the directories `rust-book`, `obsidian-help` and `cmspec`.**
`e4_uniqueness.py:12` and `anchor_eval3.py:87` hardcode those paths under
`corpora/`, **relative to the process working directory** — so invoke them from
that parent directory by absolute script path. Get either wrong and
`e4_uniqueness.py` prints `files=0  blocks>=40ch=0`, an empty table, **and exits
0** — §2.2's own named failure, in this project's own script.

`run_control.sh` takes `CORPORA` and `D8_DIR` as **environment variables**, not
flags. `--d8-dir` is `prose_merge.py`'s flag.

`--filter=blob:none` is enough for anything that only reads trees; the anchor and
uniqueness harnesses need working trees, so check out at the pin.

**blockspec#2 needs three further corpora** — `kubernetes/website`, `cncf/toc`
and `github/site-policy` — pinned in `blockspec/spike/PRE-REGISTRATION.md` §5.1
and in no `research` file, `CORPORA.md` included.

`research/CORPORA.md` lists everything the findings cite, including the benchmark
archives the differential used.

**If an agent session is sandboxed**, check that `~/.cache/uv` is writable before
reaching for `just`. A read-only cache makes every `uv run` recipe fail with
`OSError 30` *before the recipe body runs*, so no `just` target works in rowspec
or kindkit — which reads as a broken repository and is not one.

**rowspec's "1 skipped" depends on `openpyxl` being absent**, not on a flag:
`tests/test_xlsx_export.py:31` skips without it. Install the `xlsx` extra — which
a required CI check does — and the number changes, with nothing in §1 to explain
why. It is an environment fact wearing a figure's clothes.

**The suites themselves are unaffected**, once a `.venv` exists: call
`./.venv/bin/...` directly and every figure in §1 reproduces. The blocked thing
is the `uv` entry point, not the code — but note that `uv sync` *is* that entry
point, so a sandboxed session cannot create the `.venv` it then needs. Sync
first, from a session that can, and the suites run from anywhere afterwards. Do not redirect `UV_CACHE_DIR` into scratch to get around it — an empty
cache in a sandboxed session cannot populate itself, and it hides the fault from
the next session. blockspec's harness needs none of this: pure stdlib, `python3`
directly.

---

## 4. Traps that have already cost time

**`anchors=384` and `anchors=343` are the same arm on two different trees, and
the committed artifact is 343.** `results-anchor3.txt:12` prints 343, produced at
research §3's pins. `384` comes from `obsidian-help` at `a3985b58`, which is
blockspec's reconstruction of an earlier uncommitted pass. D8 §3.2 says it in as
many words — *"The 384 line belongs to `a3985b58` alone"* — and
`blockspec/spike/results/corpus-drift.txt` tabulates both. **Always name the SHA
and say which artifact you are reproducing.**

**Do not use `git rev-list --count` to decide which pin is right.** D8 §1's
header states 6,286 / 2,623 / 1,848 and those counts match `a3985b58` and
`917544888a55` — the *earlier* clone, not the one §3 pins and not the one the
committed artifacts came from. The header and the pin block describe different
trees, which is all kindspec/research#9 is about.

I got this wrong twice in one day, both times from that count. First I claimed
§3's pins were wrong and filed research#9 asking for them to be replaced. Then,
told that `results-e4.txt` only reproduces at §3's pin, I invented a "two clones
a day apart" story that kept the counts meaningful and assigned the anchor files
to `a3985b58` — which the commit dates refute outright (`a3985b58` is
2026-08-25; a clone made in September gets `327a782e`). Both versions of
research#9's acceptance would have written a false claim into the research repo,
the second into a file that was already correct.

The lesson is not about pins. A check that returns the same answer whichever
hypothesis is true cannot choose between them, and reading it as support for one
is this project's recurring defect — here committed twice, in the document that
catalogues it, by the person maintaining the catalogue. `diff` against the
committed artifact is the check that discriminates; it took two commands.

**A squash merge discards branch commit messages.** Every repository here has
`squash_merge_commit_message = PR_BODY`, so the PR description becomes the commit
and anything recorded only in a commit message is destroyed on merge. Put what
must survive in a file or in the PR body.

**A required status check is matched by job name, and a name that never reports
blocks the merge forever.** It does not lapse — it pins the pull request at
"Expected" with no bypass. Renaming a job therefore needs the ruleset edited
*first*, because the change that renames it is itself the change that cannot
merge. Requiring both names during the transition blocks everything.

**`git push --dry-run` does not evaluate server-side rules.** It reports success
against a branch that would reject the real push. To check a ruleset, read
`gh api repos/OWNER/REPO/rulesets/rule-suites`, which logs real attempts with
pass/fail, rather than the configuration.

**A same-size edit within the same second reuses the previous `.pyc`.** CPython
invalidates on `(mtime in whole seconds, size)`, so two mutations of one file can
have the second execute the first's bytecode — and a before/after hash cannot see
it, because the file did change. Run mutations with
`PYTHONPYCACHEPREFIX=$(mktemp -d)`. The loud symptom is a false SURVIVED; the
quiet one is a false *caught*.

**`awk $5` on the uniqueness output is magnitude-dependent.** Under `{:4.1f}` a
one-digit percentage is padded to `" 0.6"`, so `( 0.6%)` splits into two tokens
and a two-digit one does not. The field index is correct for some rows and wrong
for others. Parse with an anchored regex.

**The spike harness's default `--d8-dir` assumes a layout.** It looks for
`$HOME/research/experiments/D8-identity`; pass `--d8-dir` explicitly.

---

## 5. What is decided, and must not be re-litigated

- **§3, §4 and §6 of blockspec's pre-registration.** The five conditions for
  FOUND, the severity ranking with transclusion in tier A, the §4.1 tiering
  procedure, and what each outcome publishes as. Frozen.
- **Identity per kind.** Opaque row ids for rowspec, no minted ids for prose,
  named rather than positional for nodes. The prose decision rests on
  `research/design-findings/D8-identity.md` §3.3, which is now reproducible —
  100.0% within-file uniqueness for `rust-book` prose at ≥40 characters and
  99.4% for `obsidian-help`.
- **Correctness may not depend on a merge driver, a clean/smudge filter or a
  hook.** None of them travel, and a bare repository does not consult
  `.gitattributes` at all.
- **One model, several grammars.** Do not reuse one kind's syntax for another.
- **The per-directory licence split**, and why: fixtures are CC0 with no prose
  attached so they can be vendored into an implementation in any language.
- **Depend on kindkit rather than vendoring it.** Vendoring reintroduces the
  duplicated-implementation drift the kit exists to prevent, which this project
  has already caught happening twice.

---

## 6. The transferable result

Repeatedly, across mechanisms that look unrelated, a check reported a pass over
something it had never evaluated. The list below is what has been recorded; it is
the only counted list, because `AGENTS.md` §2.2 now points here rather than
carrying its own total — two hand-maintained counts in one repository diverge,
and these two had, at ten against twelve:

- a mutation gate scoring any non-zero exit as a kill, so an unimportable module
  counted as caught with nothing run
- a crash sentinel in a failing-case set doing the same thing by a different route
- a stale `.pyc` crediting one mutant with its neighbour's verdict
- `git push --dry-run` reporting success against a branch that rejects
- a conformance runner printing `0 failure(s)` over 226 unopened cases
- a mutation gate disarming itself on a reformat and reporting a pass
- `canon = identity` scoring 129 of 131
- 40 CSV-mode tests that had never run in CI for the life of the repository
- `openpyxl` collapsing an empty-text cell and an absent cell to the same read,
  making the obvious assertion vacuous
- a balance check defined as the difference it then asserted
- a guard whose denominator was subject to the control flow it measured
- a positional parse that was correct for some rows and wrong for others

The pattern is not about tables, and it is why `AGENTS.md` §2.2 is mechanical
rather than advisory: break the thing a check checks, watch it go red, put it
back. A check whose red state nobody has observed is not a check.

One refinement earned the hard way and deliberately not promoted to the contract:
a check has a **property**, a **detector**, and the **detector's inputs**, and
§2.2 as written exercises only the detector, against the one mutation whoever
wrote it happened to choose. Arming a check validates one layer and tends to
expose the next. The regress ends not by adding another check but by making the
failure structurally impossible — deriving a count from a set size rather than
accumulating it inside the loop that can skip. That is n=1 and it stays in
`blockspec/spike/LOG.md` §5.6 until it recurs somewhere the contract would bind.
