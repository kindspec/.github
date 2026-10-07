# State of play

Current as of the end of **2026-10-07**. Read `AGENTS.md` first — it is the
contract. This file is where the work actually stands, what comes next, and the
traps that have already cost time.

Every figure here names the command that produces it. Where a figure cannot be
reproduced from this checkout alone, that is said.

---

## 1. Where each repository stands

### rowspec — draft 0 released as v0.2.0, on kindkit

    410 conformance cases          find conformance/cases -name expect.json | wc -l
    0 failures, reference impl     just conform
    0 failures, second impl        just conform-alt
    74 killed, 0 survived          just mutants
    2 equivalent, 0 stale, 0 broken
    52 passed, 1 skipped           just test   (skip is openpyxl absent)
    294 files clean                just check

**All of these reproduce on 2026-10-07**, through `just` with kindkit at the
pinned `a26f8f8`. A sandboxed session that cannot run `uv` (see §3) can call the
`.venv` directly instead; the equivalents:

    ./.venv/bin/python conformance/run_cases.py
    ./.venv/bin/python conformance/run_cases.py rowspec_alt.table
    ./.venv/bin/python conformance/mutants.py
    ./.venv/bin/python -m pytest -q
    ./.venv/bin/ruff format --check . && ./.venv/bin/ruff check .

**rowspec's mutation gate is safe to kill; kindkit's is not.** rowspec writes
its mutants to `conformance/mutant_impl.py`, which is gitignored, and never edits
`reference/rowspec/table.py`, so an interrupted `just mutants` leaves the tree
clean — confirmed after a kill. That is the gate only: **an interrupted
`just test` can leave an untracked `conformance/_vacuous.py`**, which
`tests/test_conformance.py` writes and removes in a `finally`, and which is not
gitignored (`git check-ignore -v conformance/_vacuous.py` prints nothing). Delete
it if `git status` shows it. **kindkit's gate is the opposite**:
`tools/mutation_gate.py` opens each target in place and restores in a `finally`,
and its targets are tracked files spread across `kindkit/`, `tools/`,
`case-tree/` and `tests/`. A completed run is clean; a killed one leaves a
mutated tracked file. Run it in a throwaway clone, and if you do kill one,
**`git status` is the list** — do not restore from a list written down here,
which is exactly how two targets got missed when this paragraph was first
written.

**`v0.2.0` is the release to point at** (`gh release list -R kindspec/rowspec`;
`curl -s https://pypi.org/pypi/rowspec/json` gives version `0.2.0` and extra
`xlsx`). It is the first tag that contains `action.yml` — `git show
v0.1.0:action.yml` fails — and the first PyPI release that declares the `xlsx`
extra (rowspec#54). The action's self-test now installs the checkout rather than
the published wheel, so a regression in a pull request can turn
`passes-on-a-good-tree` or `fails-on-a-broken-total` red (rowspec#51); the
action's *default* install path, the one consumers use, is still exercised by no
job (rowspec#52).

The suite, the mutation gate and the case-tree convention come from kindkit,
pinned by commit in `pyproject.toml` (`grep 'kindkit @' pyproject.toml`). The
mutation probe calls `kindkit.probe_command` and reads the runner's
`--report-json` verdict rather than parsing its printed summary (rowspec#57).
What stayed is everything kindkit cannot be told — what a `parse` case means,
what `canon` asserts, how merge sides are filed.

Two numbers to carry correctly: **76 mutants are 74 distinct mutations**, because
two `(old, new)` pairs appear twice, so `74 killed` is 72 distinct kills (#48).
The second implementation (`reference/rowspec_alt/`) is the load-bearing one —
written from `SPEC.md` alone, run against the same fixture tree in CI, and right
on the last three questions where the two disagreed.

### kindkit — complete, and proven against a real consumer

    99 mutations, 99 caught, 0 survived, 0 broken    just mutants   (throwaway clone)
    145 passed                                        just test   (1 skips without node)
    21 files clean                                    just check
    6 case(s) in its own kv tree                      just cases

All of these reproduce on 2026-10-07 at `a26f8f8`, through `just` in a fresh
clone. To count tests, read pytest's own summary line; a `grep` for `def test_`
miscounts here, because one match sits inside a string literal in
`tests/test_mutation_gate.py` and parametrised tests collect as several.

**New on 2026-10-07**, all on `main`:

- **git runs with the caller's configuration stripped** (kindkit#13). A personal
  `~/.gitconfig` or `~/.config/git/attributes` with `merge=union` had been able
  to turn an expected conflict into a clean merge locally while CI, which
  carries no such config, stayed green.
- **The bytecode purge also covers `PYTHONPYCACHEPREFIX`** (kindkit#14): it
  clears beside the source and wherever the gate's interpreter caches. A probe
  subprocess that is given a *different* prefix, or a *relative* one, is still
  the probe's to own, so kindkit#11 stays open.
- **The probe contract changed** (kindkit#16). `Verdict(ran=, failures=)` is
  keyword-only and must report the set of case ids that ran; the runner's
  `--report-json PATH` writes that set and the failures as JSON; and
  `probe_command` runs a runner in a fresh interpreter and returns the `Verdict`.
  The gate refuses a failing id that is not in `ran`, and marks a mutant
  **BROKEN** if its `ran` differs from the baseline's — so a probe must run the
  whole suite every time, and a fail-fast probe turns every kill into BROKEN.

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

Verified green on 2026-10-07. The harness is **pure stdlib, run with `python3`
directly** — no `uv`, no justfile, so it works where the other two repos need a
toolchain.

`spike/PRE-REGISTRATION.md` is binding. **§3, §4 and §6 cannot be amended**, only
superseded by a new pre-registration that says why. §1, §2, §5 and §7 record
evidence and method and may be corrected, with every change logged in §8.

The merge arm's candidates are **85 records from 16 distinct cases** — one
record per mis-resolved base block per policy — and **every one is `tier:
UNASSIGNED`**. Count them with the snippet in `spike/LOG.md` §11, or:

    python3 -I -c "import json; r=[json.loads(l) for l in open('spike/results/merge-arm-candidates.jsonl')]; print(len(r), len({x['case'] for x in r}), {x['tier'] for x in r})"

§4.1 forbids whoever has seen the frequencies from assigning tiers, so tiering
is a separate job for someone who has not.

**Read `spike/README.md` "Read these before believing anything here" before
using any spike result.** Two findings bear on what comes next: `LOG.md` §9
retracts the claim that the defect needs both merge legs — one author in one
commit reproduces it — and `LOG.md` §6.2, demonstrated by
`spike/harness/oracle_limitation.py`, shows the oracle (TLLC) returning
`SURVIVED` with full confidence on repeated single-line blocks, where the truth
is undecidable.

### research — the evidence base, reproducible

Not a specification. It is the design record the three briefs cite, published so
those citations resolve. `anchor_eval*` and `e4_uniqueness` output are committed;
§3.1–3.3 can be reproduced.

**The corpora are not in the repository.** `CORPORA.md` names each one with its
source and the pins §3 records. A fresh machine has to clone them; see §3 below.

### nodespec — stub, zero work

A stub and a pointer at the org contract. No specification, no suite, no
implementation. Its brief names three concrete
`.canvas` referential-integrity holes — an override for a deleted node, an edge
to a renamed node, and two branches adding different nodes with the same name —
and calls the third the most likely home of a genuine silent-wrong merge.

### .github — the org contract and this file

### Security settings, org-wide

**Secret scanning and push protection are on for all six repositories**, and
the org enables both by default for new ones (`gh api repos/kindspec/<repo>
--jq .security_and_analysis`; `gh api orgs/kindspec`). On each of the six, a
push holding a generated AWS key pair was refused with `GH013` (.github#4,
closed); the new-repository default is read back from configuration and has
not been observed on a new repository. A never-issued `ghp_` token is *accepted*
— it is not a secret to the scanner — so test with a pattern-matched provider.

**rowspec's `pypi` environment deploys only from `v*` tags** (rowspec#55; `gh
api repos/kindspec/rowspec/environments/pypi/deployment-branch-policies`). That
is read back from configuration; no refusal has been observed yet, which is why
the issue is open.

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

1. **blockspec#2 — the duplicate-heavy arm, behind an open owner decision.**
   The corpora are named and pinned in `spike/PRE-REGISTRATION.md` §5.1. Ranked
   by evaluable human-authored cases: `kubernetes/website` is the largest arm at
   roughly 800 — an **upper** estimate extrapolated from the most recent 400 of
   23,473 merges, so enumerate before quoting it; `cncf/toc` the cleanest at 71
   with no bot involvement at all; `github/site-policy` a supporting arm at
   **21 to 25** and the only legal-text coverage. Read §5.1 for why that last
   one is a range and not a number.

   **It is not ready to run as-is.** Two things stand in the way, both recorded
   in blockspec's own `spike/README.md` and `spike/LOG.md`:
   - Those corpora are the repeated single-line-block shape on which the oracle
     is confidently wrong (`LOG.md` §6.2, `spike/harness/oracle_limitation.py`),
     so the arm needs a superseding oracle statement before its prose numbers
     can be believed.
   - The spike's strongest finding — a silent-wrong reproduced by one author in
     one commit, with no merge (`LOG.md` §9) — falls outside the frozen FOUND
     criteria, which require a stock `git merge` to create the defect
     (`PRE-REGISTRATION.md` §3, conditions 1 and 5).

   **Open, for the owner to decide**: write a superseding pre-registration
   first (and a superseding oracle statement with it), or run #2 under the
   current pre-registration as it stands. Both blockspec documents record this
   as undecided; nothing here decides it either.
2. **Tier the candidates, blind** — 16 cases, 85 records (§1). Needs someone
   who has not seen the frequencies, per §4.1.
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

Open issues carry acceptance criteria and a red-before-green requirement. List
them per repository rather than trusting a count written here:

    gh issue list -R kindspec/<repo> --state open --limit 200

Only some gate defects carry a `gate` label, so read the titles too. Closed
since the last version of this file: `kindkit#8` and `#12`, by kindkit#16.
`rowspec#44` and `#45` were gate defects and are closed — the kindkit adoption
fixed both.

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
it, because the file did change. kindkit's purge now clears both the default
`__pycache__` and the directory an inherited `PYTHONPYCACHEPREFIX` names
(kindkit#14). If you set that variable, make it **absolute** — `$(mktemp -d)`
is. A relative prefix resolves against each process's working directory, so a
probe subprocess running elsewhere caches where the purge does not look, and
nothing says so (kindkit#11, open). The loud symptom is a false SURVIVED; the quiet one is a
false *caught*.

**`awk $5` on the uniqueness output is magnitude-dependent.** Under `{:4.1f}` a
one-digit percentage is padded to `" 0.6"`, so `( 0.6%)` splits into two tokens
and a two-digit one does not. The field index is correct for some rows and wrong
for others. Parse with an anchored regex.

**The spike harness's default `--d8-dir` assumes a layout.** It looks for
`$HOME/research/experiments/D8-identity`; pass `--d8-dir` explicitly.

**Editing a file inside a uv-managed `.venv` edits it for every venv on the
machine.** uv installs by hard link from `~/.cache/uv`, so a write to an
installed file writes through to the cache entry, and every venv that later
installs that package version gets the edited copy. On 2026-10-07 an
experiment rewording `Report.summary` in an installed kindkit `e2aa334`
corrupted the cached copy, and a fresh clone of rowspec `main` then failed
`just mutants` (rowspec#57). Repaired with `uv cache clean kindkit`. `stat -c %h
<file>` above 1 means the file is a hard link. For an experiment that edits
installed code, use a private cache and copies:
`UV_CACHE_DIR=<scratch dir> UV_LINK_MODE=copy uv sync`. That is a different
case from §3's sandbox note, which is about a cache you cannot write at all.

**`gh pr edit` fails on these repositories** with a GraphQL error about
Projects (classic). Edit a pull request's body through the REST API instead:
`gh api -X PATCH repos/kindspec/<repo>/pulls/<n> -F body=@file`.

**A closing keyword in any branch commit closes the issue**, even when the PR
body says `Refs`. The squash commit carries only the PR body (see above), but
GitHub reads the branch's commits as well: kindkit#14's first commit said
`Closes #11`, and merging it closed kindkit#11, which had to be reopened. Use
`Refs` in commit messages for anything the PR does not finish.

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
- two required action checks installing the published wheel, so no regression
  in a pull request could turn them red (rowspec#51)
- a release `smoke` job whose must-fail assertion passed on *any* failure, a
  pip error included — withdrawn before it ever ran (rowspec#51 review)
- a mutant whose run skipped cases still scored equivalent, because the gate
  never compared what ran against the baseline (kindkit#16 review)

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
