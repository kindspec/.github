# State of play

Current as of **2026-10-08 (UTC)**. Read `AGENTS.md` first — it is the
contract. This file is where the work actually stands, what comes next, and the
traps that have already cost time.

Every figure here names the command that produces it. Where a figure cannot be
reproduced from this checkout alone, that is said.

---

## 1. Where each repository stands

### rowspec — v0.2.0 released; `main` is past it, and a release is being prepared

    410 conformance cases          find conformance/cases -name expect.json | wc -l
    0 failures, reference impl     just conform
    0 failures, second impl        just conform-alt
    73 killed, 0 survived          just mutants
    2 equivalent, 0 stale, 0 broken
    73 passed, 1 skipped           just test   (skip is openpyxl absent)
    296 files clean                just check

**All of these reproduce on 2026-10-08 at `ed0844b`**, in a fresh clone,
through `just`, with kindkit at the pinned `8e21b55`. They were measured with a
private uv cache (`UV_CACHE_DIR=<scratch dir> UV_LINK_MODE=copy`, §4), and
`git status` was clean after every recipe, `just mutants` included. A sandboxed
session that cannot run `uv` (see §3) can call the `.venv` directly instead;
the equivalents:

    ./.venv/bin/python conformance/run_cases.py
    ./.venv/bin/python conformance/run_cases.py rowspec_alt.table
    ./.venv/bin/python conformance/mutants.py
    ./.venv/bin/python -m pytest -q
    ./.venv/bin/ruff format --check . && ./.venv/bin/ruff check .

**The gate has 75 mutants, all distinct, and refuses a duplicate** (rowspec#64).
`73 killed` plus `2 equivalent` is all of them; the two equivalents carry their
claims as fields on the mutant. The earlier "76 mutants are 74 distinct" caveat
no longer applies.

**rowspec's mutation gate is safe to kill; kindkit's is not.** rowspec writes
its mutants to `conformance/mutant_impl.py`, which is gitignored, and never edits
`reference/rowspec/table.py`, so an interrupted `just mutants` leaves the tree
clean. That is the gate only: **an interrupted `just test` can leave an
untracked `conformance/_vacuous.py`**, which `tests/test_conformance.py` writes
and removes in a `finally`, and which is not gitignored (`git check-ignore -v
conformance/_vacuous.py` prints nothing). Delete it if `git status` shows it.
**kindkit's gate is the opposite**: `tools/mutation_gate.py` mutates tracked
files in place and restores them in a `finally`. A completed run is clean; a
killed one leaves a mutated tracked file. Run it in a throwaway clone, and if
you do kill one, **`git status` is the list** — do not restore from a list
written down here.

**CI.** `check.yml` has three jobs. `conformance` runs lint, `just test` with
the extra absent, and the example recipe. `xlsx-extra` runs `just test-xlsx`.
`kind` calls kindkit's reusable workflow at the pinned commit and reports as
**`kind / conformance`** (rowspec#78). That workflow runs four gates: the case
tree against kindkit's convention, the suite, the second implementation, and
the mutation gate, judged by the gate's own report.
`tests/test_pins.py` fails if the workflow's commit and the package pin differ.
`action-selftest.yml` supplies `passes-on-a-good-tree` and
`fails-on-a-broken-total`, against the checkout (rowspec#51). `check.yml` and
`action-selftest.yml`, the two workflows that produce required checks, run on
`push` to `main` only, plus `pull_request`, so each required check has one
producer (rowspec#67). `release.yml` runs on `v*` tags, and
`action-published.yml` only when called by it or dispatched by hand. Every
action is pinned to a commit, and a test keeps it so (rowspec#71).

**Landed since v0.2.0**, all on `main` (`gh api
repos/kindspec/rowspec/compare/v0.2.0...main --jq .ahead_by` prints 19). These
are highlights; `CHANGELOG.md` `[Unreleased]` is authoritative.

- **The probe.** The mutation probe calls `kindkit.probe_command` and reads the
  runner's `--report-json` verdict rather than parsing its printed summary
  (rowspec#57).
- **Fixes.** CSV mode warns on a lone CR and accepts CRLF, per SPEC §13
  (rowspec#60). The runner exits 2 when the implementation will not import
  (rowspec#62). The import-boundary test sees `__import__` and `import_module`
  with a constant name (rowspec#65).
- **Release gate.** The build fails when `__version__` disagrees with the
  metadata (rowspec#69), and the release gate runs `just test` and
  `just test-xlsx` (rowspec#70).
- **The action's default install path.** `action-published.yml` runs the action
  exactly as a consumer does, after each release's `publish`, and by hand
  (rowspec#72). It has run only on throwaway branches so far, never after a
  real release.
- **Removed.** `corpus_check.py` is gone: it never opened a `.mdtbl` file, so
  it could not fail (rowspec#68).
- **Licensing.** SPDX headers, per-directory `LICENSE` files, and
  `tests/test_licensing.py` checking both (rowspec#74).
- **CI and tooling.** The extra-absent guard runs with `--exact`, like the
  step it guards (rowspec#66), and pre-commit runs the ruff the project locks
  (rowspec#73).
- **Docs.** Stale claims about refusals, reserved cases and `just test`
  corrected (rowspec#58). How to run the suite from the sdist, and why pip
  cannot (rowspec#75). rowspec#47 stays open.
- **The kindkit pin.** Moved to `bf716e3`, `v0.1.0`'s commit (rowspec#76),
  then to `8e21b55` (rowspec#77), then the adoption of kindkit's workflow above
  (rowspec#78).

**A release of these is being prepared, as 0.3.0 (rowspec#80, open). Tagging
needs the owner's approval first**, because a `v*` tag is what publishes to PyPI. Until then, `v0.2.0` is the release to point at
(`gh release list -R kindspec/rowspec`; `curl -s
https://pypi.org/pypi/rowspec/json` gives version `0.2.0` and extra `xlsx`).

The suite, the mutation gate and the case-tree convention come from kindkit,
pinned by commit in `pyproject.toml` (`grep 'kindkit @' pyproject.toml`). What
stayed in rowspec is everything kindkit cannot be told — what a `parse` case
means, what `canon` asserts, how merge sides are filed. The second
implementation (`reference/rowspec_alt/`) is the load-bearing one — written from
`SPEC.md` alone, run against the same fixture tree in CI, and right on the last
three questions where the two disagreed.

### kindkit — tagged v0.1.0, called by rowspec's CI, no open issues

    148 mutations, 148 caught, 0 survived, 0 broken   just mutants   (throwaway clone)
    220 passed                                         just test   (a test skips without node)
    28 files clean                                     just check
    6 case(s) in its own kv tree                       just cases

All of these reproduce on 2026-10-08 at `8e21b55`, through `just` in a fresh
clone with a private uv cache. To count tests, read pytest's own summary line;
a `grep` for `def test_` miscounts here, because parametrised tests collect as
several.

**`v0.1.0` is older than `main`.** The tag peels to `bf716e3`
(`git ls-remote --tags https://github.com/kindspec/kindkit`), and `main` is
ahead of it (`gh api repos/kindspec/kindkit/compare/v0.1.0...main --jq
.ahead_by`). The workflow contract below — the report's `root`,
`KINDKIT_REPORT_JSON`, `KINDKIT_GATE_REPORT` — is on `main` and not in the
tag, which is why rowspec pins `8e21b55` by commit. kindkit is not on PyPI
(`curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/kindkit/json`
prints 404).

**Landed in kindkit#13 to kindkit#24**, all on `main`:

- **git runs with the caller's configuration stripped** (kindkit#13), and a
  failed git call raises instead of being read as a verdict (kindkit#21).
- **Stale bytecode.** The purge covers `PYTHONPYCACHEPREFIX` (kindkit#14), and
  every scratch write is dated with its own mtime second (kindkit#23). A `.pyc`
  from an earlier write then fails validation wherever it was cached. What a
  probe still owns is listed in kindkit's README, "What a probe has to get
  right".
- **The probe contract** (kindkit#16). `Verdict(ran=, failures=)` is
  keyword-only and must report the set of case ids that ran. The runner's
  `--report-json PATH` writes that set and the failures as JSON, and
  `probe_command` runs a runner in a fresh interpreter and returns the
  `Verdict`. A mutant whose `ran` differs from the baseline's is **BROKEN**, so
  a probe must run the whole suite every time.
- **Failure paths.** A non-UTF-8 fixture is a tree fault, exit 2, not a case
  failure (kindkit#20). A byte splice that breaks the JSON it mutates is
  refused (kindkit#22). The pre-commit ruff is the locked one (kindkit#19).
- **The reusable workflow** (kindkit#24). `.github/workflows/kind.yml`, with
  `tools/conform.py` for the two suite steps and `tools/check_gate.py` for the
  mutation step. A suite passes only if its report names the fixture root and
  ran exactly the case directories under it. The check name, `<calling job> /
  conformance`, is an interface. kindkit calls it on its own toy tree, and
  rowspec calls it at `8e21b55`. This was kindkit#4, the last v0 item.

Three pieces besides the workflow: the tree-driven runner, the case-tree
convention under CC0, and the mutation gate a kind runs against its own
implementation. rowspec adopting it kept every number identical, which is the
only evidence that the abstraction is real rather than fitted.

**The gate is Python-only** — `tokenize`, `ast`, `compile`. A kind whose
reference implementation is not Python gets the runner and not the gate.

### blockspec — pre-registration 2 binding, harness in review, no arm run

    SELECTION-GUARD SELFTEST: PASS      python3 spike/harness/prose_merge.py --selftest-selection
    SELFTEST: PASS                      python3 spike/harness/check_control_gate.py --selftest
    PLANTED-CASE GATE: PASS             python3 spike/harness/prose_merge.py --plant --d8-dir <research>/experiments/D8-identity

Verified green on 2026-10-08 at `f59c109`, in a fresh clone. The harness is
**pure stdlib, run with `python3` directly** — no `uv`, no justfile.

**`spike/PRE-REGISTRATION-2.md` is merged (blockspec#15) and binding for
blockspec#2. The owner approved it on 2026-10-07, before it merged** (the
merge is at 2026-10-07T23:28:22Z: `gh api repos/kindspec/blockspec/pulls/15
--jq .merged_at`). It supersedes
`PRE-REGISTRATION.md`, which stays unchanged as the record. Its §0 lists the
twenty choices the approval covers, each with its alternative. **Its own header
still reads "Status: DRAFT, for owner approval", and `spike/LOG.md` §13 still
says it is not binding until approved.** Both were written before the approval,
so read them as stale.

**The cheap measurement has landed** (blockspec#14). It ran research's D8
anchor and uniqueness harnesses on the §5.1 corpora, with output in
`spike/results/cheap-arm/` and the log in `LOG.md` §12. It decides nothing by
itself; it is input to pre-registration 2.

**The harness for pre-registration 2 is in review on a draft pull request**
(blockspec#16, "do not merge"). Under that document's §9, the harness at its
validation commit is the implementation, and that commit does not exist yet.
**No arm has run** — not Arm 0, E, S or M (§6.5), nor the R mechanism, the
exporter or the tierer.

**The first run's 85 merge-arm records are not tiered.** That is
pre-registration 2 §0 item 17, approved, and it reverses item 3 of the previous
version of this file's §2. The records remain as the first registration's
output: 85 records from 16 distinct cases, every one `tier: UNASSIGNED`.

    python3 -I -c "import json; r=[json.loads(l) for l in open('spike/results/merge-arm-candidates.jsonl')]; print(len(r), len({x['case'] for x in r}), {x['tier'] for x in r})"

**Read `spike/README.md` "Read these before believing anything here" before
using any spike result.** `LOG.md` §9 retracts the claim that the defect needs
both merge legs — one author in one commit reproduces it — and `LOG.md` §6.2,
demonstrated by `spike/harness/oracle_limitation.py`, shows the oracle (TLLC)
returning `SURVIVED` with full confidence on repeated single-line blocks, where
the truth is undecidable.

### research — the evidence base, reproducible

Not a specification. It is the design record the three briefs cite, published so
those citations resolve. `anchor_eval*` and `e4_uniqueness` output are committed;
§3.1–3.3 can be reproduced.

**research has no open issues** (`gh issue list -R kindspec/research --state
open` prints nothing). research#15, that the D8 harnesses neither recorded nor
checked which commit each corpus was at, was settled by research#16; §3 says
what that changes. Third-party sample files are attributed in `NOTICE`, with full licence
texts in `LICENSES/` (research#13). `CORPORA.md` records that committed output
quotes Enron content (research#14). The D8 harnesses fail loudly when they
cannot read a corpus (research#11).

**The corpora are not in the repository.** `CORPORA.md` names each one with its
source and the pins §3 records. A fresh machine has to clone them; see §3 below.

### nodespec — stub, zero work

A stub and a pointer at the org contract. No specification, no suite, no
implementation. Its brief names three concrete
`.canvas` referential-integrity holes — an override for a deleted node, an edge
to a renamed node, and two branches adding different nodes with the same name —
and calls the third the most likely home of a genuine silent-wrong merge.

### .github — the org contract, this file, the org page, the audit

`AGENTS.md`, `STATE.md`, `profile/README.md`, the default issue forms, and
`scripts/check_required_checks.py`.

**The required-checks audit exits 0 on the org.** On 2026-10-08, with the
DUPLICATE rule of .github#16 and .github#18:

    $ python3 -I scripts/check_required_checks.py --public-only
    1 private repositories skipped (--public-only)
    6 repositories, 7 workflows, 7 pull_request jobs, 7 required checks: 0 finding(s), 0 not evaluated

.github#15 taught the script to expand a job that calls a reusable workflow
into one `<caller> / <called job>` context per called job. A call into another
repository is read at exactly its pinned ref and kept in the `--save`
snapshot, so kindkit's and rowspec's `kind` jobs now match their required
`kind / conformance`. It still refuses, exit 2, a call it cannot fetch and a
called workflow that itself calls one. .github#12 runs the audit daily.

**One producer per required check, in kindkit too.** kindkit#26 moved
kindkit's `check.yml` to `push` on `main` only, plus `pull_request`, as
rowspec#67 did for rowspec: a pull request head carries `check` and
`kind / conformance` once each, from the `pull_request` suite. `main` still
gets a push run. On kindkit#26's merge commit `6ebd80d`, `gh api
repos/kindspec/kindkit/commits/<sha>/check-runs` lists `check` and
`kind / conformance` from one `push` suite, both `success`.

**The audit now sees a second producer.** A required context whose workflow
also runs on `push` to some branch other than the default — the defect
kindkit#26 and rowspec#67 removed by hand — is a DUPLICATE finding, exit 1
(.github#16). It reads `push` with no branch filter, `branches-ignore`, and
`branches` with GitHub's `*`, `**`, `?`, `+`, `[]` and `!`, and the caller's
`push` decides for a called workflow's contexts. A tags-only `push` does not
count. A filter it cannot settle, it refuses with exit 2. Restoring kindkit's
old `on: [push, pull_request]` in a `--save` snapshot of the org gives two
DUPLICATE findings, `check` and `kind / conformance`.

**It also sees a producer in another workflow** (.github#18). A required
context produced on `pull_request` by one workflow, and on `push` to some other
branch by a job of the same context in a different active workflow, is also a
DUPLICATE, and the finding names both workflows. The `push` side uses the same
filter evaluation and refusals, and expands a called workflow into its
`<caller> / <called>` contexts. A `push` job there whose context it cannot
resolve (a matrix, an expression or block name, or a call it cannot read) is
refused, exit 2. The issue's reproduction, a `push.yml` with
`on: push` and a job `check` added to kindkit in a `--save` snapshot, gives one
DUPLICATE for `check`.

**What it still does not see: two `pull_request` producers.** Two workflows
that both run a job of the same name on `pull_request` also give a required
context two suites. Nothing flags that yet.

#### Security settings, org-wide

**Secret scanning and push protection are on for all six repositories**, and
the org enables both by default for new ones (`gh api repos/kindspec/<repo>
--jq .security_and_analysis`; `gh api orgs/kindspec`). On each of the six, a
push holding a generated AWS key pair was refused with `GH013` (.github#4,
closed); the new-repository default is read back from configuration and has
not been observed on a new repository. A never-issued `ghp_` token is *accepted*
— it is not a secret to the scanner — so test with a pattern-matched provider.

**Two-factor authentication is required for every org member** (`gh api
orgs/kindspec --jq .two_factor_requirement_enabled` prints `true`). That is read
back from configuration.

**rowspec's `pypi` environment deploys only from `v*` tags** (rowspec#55; `gh
api repos/kindspec/rowspec/environments/pypi/deployment-branch-policies`). That
is read back from configuration; no refusal has been observed yet, which is why
the issue is open.

**Re-checked on 2026-10-08**, by reading configuration back:
`security_and_analysis` shows secret scanning and push protection `enabled` on
all six repositories; `gh api orgs/kindspec` shows two-factor required and both
new-repository defaults `true`; and the `pypi` environment's only deployment
policy is `tag v*`. Nothing above changed. **Required checks did change** on
rowspec and kindkit, each gaining `kind / conformance`; `AGENTS.md` §3.1 has the
table.

---

## 2. What comes next

**blockspec is trending toward "do not build this," and that is a deliverable.**
D8 records zero typed-prose silent-wrongs under the hardened policy across five
arms. The spike retracted its own central claim — that the defect needs both
merge legs to act — and the retraction makes D8 *stronger* evidence against,
because the shape turns out to be single-leg reachable and D8's arms would have
caught it. Pre-registration 2 now decides it, and both outcomes are
deliverables.

### Owner decisions

Settled, and concerning the public work. Each draft named below is approved by
the owner **before** it is committed.

- **blockspec#2 runs under `spike/PRE-REGISTRATION-2.md`**, merged and approved
  (§1). Nothing in its §0 is open; to change a choice now means superseding
  again, not editing.
- **nodespec gets its own pre-registered spike**, once blockspec#2 is set up. It
  does not wait for blockspec to resolve.
- **A fresh agent behind an information barrier satisfies both independence
  rules**: the suite-author rule (`AGENTS.md` §2.1) and blind judgement under a
  pre-registration. The barrier is an exported directory holding only the
  permitted files and no `.git` — a `git archive` of the allowed paths, not a
  worktree, which shares the object store and reaches every commit (`git -C
  <worktree> show main:<path>` prints a file the worktree has deleted). The
  agent gets no copy of the authoring conversation. Network access is
  honour-system: every kindspec repository is public. What each agent was given
  is logged in the repository it works on.
- **rowspec's spec-shape questions are deferred, and tracked**: conformance
  fixtures for CSV mode in rowspec#63; stable identifiers for the §9 refusals in
  rowspec#61, which counts the parse cases that accept a refusal for any reason
  (`grep -rl '"refusal_contains": ""' conformance/cases | wc -l`, run in
  rowspec).
- **kindkit goes to PyPI once its contracts have a second consumer.** It is
  tagged `v0.1.0` and not published (§1).
- **A rowspec release is tagged only with the owner's approval** (§1).

In order:

1. **blockspec#2 — review the pre-registration 2 harness (blockspec#16).** Then
   come the validation commit its §9 binds, and the arms in the order the
   document sets, Arm 0 first. Nothing runs before the validation commit.
2. **nodespec's existential spike — draft its pre-registration**, once
   blockspec#2 is set up. The owner approves the draft before
   commit. Its brief argues the rowspec thesis does not transfer to canvases at
   all, and that a finding of "do not build this" is a legitimate outcome there
   too.
3. **rowspec 0.3.0** (rowspec#80), once the owner approves tagging (§1).
4. **blockspec#3 and #4 — the adjudications.** djot versus markdown, and what a
   block is. Both are non-empirical, so §4 of the contract applies: two
   independent arguments from the same evidence, and the adjudication written
   into the repository with its reversal cost.
5. **blockspec#5 — author the case tree before any implementation exists.** The
   §0 decision, and the one discipline rowspec had to retrofit.

Open issues carry acceptance criteria and a red-before-green requirement. List
them per repository rather than trusting a count written here:

    gh issue list -R kindspec/<repo> --state open --limit 200

Only some gate defects carry a `gate` label, so read the titles too. Closed
since the last version of this file:

- kindkit: every issue it had open — kindkit#3, #4, #9, #10, #11, #15 and
  #17 (`gh issue list -R kindspec/kindkit --state open` prints nothing);
- rowspec: rowspec#39, #40, #42, #43, #48, #49, #52, #56 and #59;
- research: research#4, #6 and #15.

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
that parent directory by absolute script path. Get either wrong and both
harnesses now exit 1 naming the directory git could not enter (research#11);
before that fix, `e4_uniqueness.py` printed an empty table and exited 0.

`run_control.sh` takes `CORPORA` and `D8_DIR` as **environment variables**, not
flags. `--d8-dir` is `prose_merge.py`'s flag.

`--filter=blob:none` is enough for anything that only reads trees; the anchor and
uniqueness harnesses need working trees, so check out at the pin.

**The D8 harnesses refuse a corpus that is off its pin** (research#16).
`experiments/D8-identity/corpus_pin.py` holds the three pins above. Before
reading a corpus, every D8 harness prints its HEAD to stderr, so stdout stays
byte-identical to the committed results. It exits non-zero when HEAD is not
the pin, or when tracked files differ from HEAD; untracked files do not count.
`D8_ALLOW_UNPINNED=1` overrides it for a run meant for another tree, such as
blockspec's `a3985b58` control arm, and prints a warning naming the pin.

**blockspec#2's corpora are seven arms over six repositories**, in
pre-registration 2 §6.2: `rust-book`, `obsidian-help` and `cmspec` at D8 §3's
pins above, and `kubernetes/website` (as `k8s-en` and `k8s-l10n`), `cncf/toc`
and `github/site-policy` at the first registration's §5.1 pins. Those last three
are in no `research` file, `CORPORA.md` included.

`research/CORPORA.md` lists everything the findings cite, including the benchmark
archives the differential used.

**If an agent session is sandboxed**, check that `~/.cache/uv` is writable before
reaching for `just`. A read-only cache makes every `uv run` recipe fail with
`OSError 30` *before the recipe body runs*, so no `just` target works in rowspec
or kindkit — which reads as a broken repository and is not one.

**rowspec's "1 skipped" depends on `openpyxl` being absent**, not on a flag:
`tests/test_xlsx_export.py` skips without it. `just test` runs `uv run
--exact`, which removes `openpyxl` even if you installed the extra, so its
figure does not move. The skip changes only where pytest runs with the extra
present — `just test-xlsx`, or CI's required `xlsx-extra` job — and a bare
`./.venv/bin/python -m pytest` in a venv that has the extra changes it too,
with nothing in §1 to explain why. It is an environment fact wearing a figure's
clothes.

**The suites themselves are unaffected**, once a `.venv` exists: call
`./.venv/bin/...` directly and every figure in §1 reproduces. The blocked thing
is the `uv` entry point, not the code — but note that `uv sync` *is* that entry
point, so a sandboxed session cannot create the `.venv` it then needs. Sync
first, from a session that can, and the suites run from anywhere afterwards.
Do not redirect `UV_CACHE_DIR` into scratch to get around it — an empty
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
trees, which is all kindspec/research#9 was about.

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

**A stacked pull request whose base was squash-merged will not update cleanly.**
The squash commit on `main` holds the base branch's changes under a new hash,
so merging `main` into the stacked branch replays the same edits twice and
conflicts. The org forbids force-push, so a rebase is not available. Merge
`main` into the branch and resolve each conflict by hand, taking `main`'s side
for whatever the base already landed. Better, do not stack: branch the second
change from `main` once the first has merged.

**Strict mode plus several pull requests that touch the same file means serial
conflicts.** With "require branches to be up to date", each merge makes every
other open pull request out of date. Where they all edit one region, typically
`CHANGELOG.md`'s `[Unreleased]`, each also conflicts with the one just merged.
Land them one at a time, merging `main` and resolving before each, and expect
to rerun CI for every one.

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
it, because the file did change. kindkit now dates every scratch write with its
own mtime second (kindkit#23), which defeats a `.pyc` wherever it was cached,
and still purges the two places it can see (kindkit#14). A gate of your own that
writes a file and re-imports it has the same problem; kindkit's README, "What a
probe has to get right", lists what the stamp does not reach. The loud symptom
is a false SURVIVED; the quiet one is a false *caught*.

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

**`gh pr edit`, `gh pr view` and `gh issue view` fail with the gh 2.46.0 on
this machine**, exiting 1 with a GraphQL error about Projects (classic) — a property of that gh version,
not of the repositories. Use the REST API: `gh api -X PATCH
repos/kindspec/<repo>/pulls/<n> -F body=@file` to edit a pull request's body,
`gh api repos/kindspec/<repo>/pulls/<n>` to read one, and `gh api
repos/kindspec/<repo>/issues/<n>` plus `.../issues/<n>/comments` to read an
issue.

**GitHub matches a closing keyword even when the sentence negates it.**
kindkit#14's body — which became its squash commit — has the heading
`## Not done: why this does not close #11`, and merging it closed kindkit#11,
which had to be reopened. GitHub lists #11 among that PR's closing references
(`gh api graphql -f query='{repository(owner:"kindspec",name:"kindkit"){pullRequest(number:14){closingIssuesReferences(first:10){nodes{number}}}}}'`).
Never write `close`, `closes`, `fix`, `fixes`, `resolve` or `resolves`
followed by `#N` in a PR body or a commit message unless that issue should
close — not even negated: "does not resolve #N" contains `resolve #N` and
matches. Keep the keyword away from the number, as in `Refs #N (not finished
here)`, and run that query on every pull request you open. It caught the same
heading shape again in .github#12, whose first body had the heading "why this
does not close #3"; the body was rewritten before anything merged.

---

## 5. What is decided, and must not be re-litigated

- **§3, §4 and §6 of blockspec's first pre-registration**, and now
  **pre-registration 2 as a whole**. The sanctioned route past a frozen
  pre-registration is superseding: a new one that says why, never an edit.
  blockspec#2 took that route, and pre-registration 2 is what binds it (§1).
- **A fresh agent behind an information barrier counts as independent**, for
  the suite-author rule and for blind judgement under a pre-registration, with
  what it was given logged (§2, and `AGENTS.md` §2.1 for what the barrier is).
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
  has already caught happening twice. That covers its CI too: a kind calls
  `kind.yml`, at the commit it pins the package to.

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
- a differential harness whose injected defect silently stopped applying
- a guard whose denominator was subject to the control flow it measured
- a positional parse that was correct for some rows and wrong for others
- two required action checks installing the published wheel, so no regression
  in a pull request could turn them red (rowspec#51)
- a release `smoke` job whose must-fail assertion passed on *any* failure, a
  pip error included — withdrawn before it ever ran (rowspec#51 review)
- a mutant whose run skipped cases still scored equivalent, because the gate
  never compared what ran against the baseline (kindkit#16 review)
- a CI suite step passing a runner that had read a different tree with the
  same case names, or fallen back to its default tree, because it compared
  case names and never the root they were read from (kindkit#24 review)
- a CI mutation step accepting any exit 0, so `true` passed as a mutation gate
  that had run nothing (kindkit#24 review)
- a required-checks audit reporting 0 findings for a required check produced
  only by `merge_group`, `pull_request_target`, or a `pull_request` filtered to
  another branch, none of which ever reports on the pull request it gates
  (.github#10 review; reproduced with `--load` against that pull request's
  first commit, `0970870`)
- the same audit reporting 0 findings while kindkit's required `check` and
  `kind / conformance` ran twice on a pull request head, once from a bare
  `push` and once from `pull_request`, because it read only the
  `pull_request` trigger (.github#16; on kindkit#25's head `79d194a`)
- the same audit, with that fixed, still reporting 0 findings when the second
  producer was a `push` job of the same name in a different workflow, because
  it read only each workflow's own `push` (.github#18; reproduced with `--load`
  on a `--save` snapshot with a `push.yml` added to kindkit)
- `corpus_check.py`, a green CI step in rowspec that never opened a `.mdtbl`
  file and printed `0 identified artifact(s), 0 duplicate id(s)` on rowspec's
  own tree (rowspec#68)

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
