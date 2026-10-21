# State of play

Current as of **2026-10-21 (UTC)**. A figure measured earlier says when, and
at which commit. Read `AGENTS.md` first — it is the contract. This file is
where the work actually stands, what comes next, and the traps that have
already cost time.

Every figure here names the command that produces it. Where a figure cannot be
reproduced from this checkout alone, that is said.

---

## 1. Where each repository stands

### rowspec — v0.4.0 released to PyPI; `main` 48 commits ahead of it

    631 conformance cases          find conformance/cases -name expect.json | wc -l
    281 CSV-profile cases          find conformance/cases-csv -name expect.json | wc -l
    0 failures across 631          just conform        (reference impl)
    0 failures across 631          just conform-alt    (second impl)
    0 failures across 281          just conform-csv    (CSV profile)
    114 killed, 0 survived         just mutants
    2 equivalent, 0 stale, 0 broken
    85 killed, 0 survived          just mutants-csv    (--profile csv)
    3 equivalent, 0 stale, 0 broken
    41 killed, 0 survived          just mutants-csv    (--profile sidecar)
    0 equivalent, 0 stale, 0 broken
    1642 passed, 2 skipped         just test   (both skips are openpyxl absent)
    62 passed                      just test-xlsx
    1 passed                       just test-libreoffice   (soffice on PATH)
    857 files clean                just check

**All of these reproduce on 2026-10-21 at `8cb32c9`** (rowspec#271's merge),
in a fresh clone, through `just`, with kindkit at the pinned `8e21b55`
(`grep 'kindkit @' pyproject.toml`). They were measured with a private uv
cache (`UV_CACHE_DIR=<scratch dir> UV_LINK_MODE=copy`, §4), and `git status
--short` printed nothing after the mutation gates. The two skips are
`tests/test_xlsx_export.py` and `tests/test_xlsx_libreoffice.py`, each "could
not import 'openpyxl'" (`uv run --exact pytest -q -rs` on those two files). A
sandboxed session that cannot run `uv` (see §3) can call the `.venv`
directly instead; the equivalents:

    cd conformance && ../.venv/bin/python run_cases.py
    cd conformance && ../.venv/bin/python run_cases.py rowspec_alt.table --profile mdtbl
    cd conformance && ../.venv/bin/python run_cases.py --profile csv
    cd conformance && ../.venv/bin/python mutants.py [--profile csv|sidecar]
    ./.venv/bin/python -m pytest -q
    ./.venv/bin/ruff format --check . && ./.venv/bin/ruff check .

**What `main` has beyond `v0.4.0`** (`gh api
repos/kindspec/rowspec/compare/v0.4.0...main --jq '.ahead_by'` prints 48 on
2026-10-21; `--jq '.commits[].commit.message|split("\n")[0]'` lists them).
`CHANGELOG.md` `[Unreleased]` is authoritative; the highlights:

- **`rowspec.edit`, an editing API for `.mdtbl` files**: text in, text out,
  changing only the lines an operation is about, and refusing an edit whose
  input or result SPEC.md refuses, with that refusal's §9 identifier.
  `rowspec add-row` gains `--id`, `--after`, `--before` and `--end`, and
  `add-column`, `delete-column` and `rename-column` edit through it.
  `docs/editing-api.md` has the design.
- **xlsx export takes `--values`** (rowspec#89), writing `rowspec eval`'s
  computed values in place of formulas.
- **`evaluate_bytes(data)` in both implementations** (rowspec#222), refusing
  bytes that are not UTF-8 as `bad-encoding` before anything else, with the
  first case that asserts `bad-encoding` alone.
- **Identifiers end to end.** `rowspec check` and `rowspec eval` print a
  refused file's §9 identifier (rowspec#101); SPEC.md §13 gives every
  CSV-profile refusal one, and §9 gains entry 27, `column-type-mismatch`
  (rowspec#103); and cases assert identifiers that no parse case asserted
  alone (rowspec#99). No `expect.json` under `conformance/cases-csv/`
  carries `refusal_contains` on `main` (`git grep -l '"refusal_contains"'
  origin/main -- 'conformance/cases-csv/**/expect.json' | wc -l` prints 0).
- **CLI and CSV-mode fixes**, listed under `[Unreleased]` `### Fixed`.

**What 0.4.0 carries beyond 0.3.0.** `CHANGELOG.md` `[0.4.0]` is
authoritative; these highlights were written when they were still
unreleased:

- **Stable refusal identifiers** (rowspec#87, closing rowspec#61). Every
  SPEC.md §9 entry opens with a name such as `duplicate-row-id` or `lone-cr`,
  and an implementation MUST report it with the refusal.
  Refusing `parse` cases assert `refusal` instead of `refusal_contains`:
  no `expect.json` under `conformance/cases/` carries `refusal_contains` at
  `v0.4.0` (`git grep -l refusal_contains v0.4.0 --
  'conformance/cases/**/expect.json' | wc -l` prints 0). **This is a
  breaking change** for any implementation that does not report
  identifiers. §9 also gained
  `order-without-key` (entry 25) and split encoding into `bad-encoding` and
  `leading-bom`.
- **The CSV profile** (SPEC.md §13). A case tree of its own,
  `conformance/cases-csv/`, run by `--profile csv` (rowspec#85, #91, #98),
  with a mutation gate over `csvmode.py` (rowspec#95). §13 now states how the
  profile reads RFC 4180 record boundaries, stray quotes (rowspec#96, #97),
  empty-name duplicates (rowspec#104, closing #92) and column-name trimming,
  ASCII space and tab only (rowspec#123, closing #118). rowspec#63 is closed.
  **In 0.4.0 the CSV profile does not carry §9's identifiers**: its cases
  assert `refusal_contains` (129 files, `git grep -l '"refusal_contains"'
  v0.4.0 -- 'conformance/cases-csv/**/expect.json' | wc -l`), and SPEC.md
  §13 says so. `main` has since given them identifiers (rowspec#103, above).
- **xlsx export writes live formulas** (rowspec#84, part of rowspec#35):
  computed columns as structured-reference formulas, unfiltered declarations
  as `SUBTOTAL`, and a `NotExpressible` refusal for what a spreadsheet cannot
  say. The exported workbook is recalculated by LibreOffice and compared with
  `rowspec eval` (rowspec#86, closing #36). rowspec#35 stays open for the
  filtered and group aggregates.
- **Fixes and spec rulings of 2026-10-14/15** (rowspec#104 to #138). Each
  closed issue below was closed by the PR named (`gh api graphql` on each
  PR's `closingIssuesReferences`):
  - overflow: an infinite aggregate operand (rowspec#105) and an infinite
    row operand (rowspec#109, closing #107) are `#REF!(overflow)`; a numeric
    literal beyond binary64 is `#REF!(overflow)` in every row, and a header
    error outranks a row error (rowspec#122, ruling on #117);
  - keys: `key :=` naming no stored column is `malformed-declaration`
    (rowspec#108), so is `key := fn(col)` (rowspec#121, ruling on #110), and a
    blank key value is `bad-identifier` (rowspec#127, closing #111);
  - `#REF!` choice: an aggregate over several distinct `#REF!` values carries
    one chosen by a fixed ranking, never by row position (rowspec#125, ruling
    on #115); `delta(c)` carries this row's error when both rows give one
    (rowspec#124, ruling on #116);
  - `prior()` over stored text is `#REF!(c)` (rowspec#128, closing #114; the
    same change stopped trimming U+00A0 from an order column, and #136 was
    closed on it); a stored cell spelled like `#REF!` is text (rowspec#129,
    closing #126); a computed cell holding only a Unicode space is refused
    (rowspec#139, closing #137);
  - two disagreements between the reference and `rowspec_alt` settled
    (rowspec#106); cases for the above (rowspec#119, closing #100 and
    #102; rowspec#138) and mutants (rowspec#120).

**CI.** `check.yml` has four jobs. `conformance`, a Python 3.11 and 3.12
matrix, runs `just check`, `just test` with the extra absent, `just
conform-csv`, `just mutants-csv` and the example recipe, and
`conformance-all` reports it under the required name `conformance`.
`xlsx-extra` runs `just test-xlsx`, installs LibreOffice and runs `just
test-libreoffice`. `kind` calls kindkit's reusable
workflow at `8e21b55` and reports as **`kind / conformance`**: the case tree
against kindkit's convention, the suite, the second implementation and the
mutation gate. `action-selftest.yml` supplies `passes-on-a-good-tree` and
`fails-on-a-broken-total`. Both workflows run on `push` to `main` only, plus
`pull_request` (`grep -n -A3 '^on:' .github/workflows/*.yml`). On `8cb32c9`
every check run is `success` (`gh api
repos/kindspec/rowspec/commits/8cb32c9/check-runs --jq
'.check_runs[]|"\(.name) \(.conclusion)"'`). `release.yml` runs on `v*`
tags.

**0.4.0 is released.** The tag `v0.4.0` peels to `65a7841` (`git ls-remote
--tags https://github.com/kindspec/rowspec`), PyPI has `0.4.0` (`curl -s
https://pypi.org/pypi/rowspec/json`), and its GitHub Release is marked
Latest, published 2026-10-16T01:30:40Z (`gh release list -R
kindspec/rowspec`; `gh api repos/kindspec/rowspec/releases/tags/v0.4.0 --jq
.published_at`). No later tag exists.

**The mutation gates are safe to kill.** `just mutants` writes its mutants to
`conformance/mutant_impl.py`, and `just mutants-csv` to
`conformance/mutant_csvmode.py` and `conformance/mutant_sidecar.py`; all
three are gitignored (`git check-ignore -v` names `.gitignore:45`, `:46`
and `:47`), and none edits a tracked file. Each run holds an exclusive
`flock` on `conformance/.mutants.lock`, so a second gate in the same tree
waits, and a leftover scratch file while the lock is held can
only be a killed run's: the gate refuses it, exit 2, and names it. Delete it
and rerun. **An interrupted `just test` can leave an untracked
`conformance/_vacuous.py`**, which `tests/test_conformance.py` writes and
removes in a `finally`, and which is not gitignored. Delete it if `git status`
shows it.

**Open issues** (`gh issue list -R kindspec/rowspec --state open --limit
200`, on 2026-10-21):

- editing: rowspec#272 (`set_formula` centres a formula padded on both
  sides), filed 2026-10-21;
- xlsx export: rowspec#35 (filtered and group aggregates, labelled
  `blocked`), #83 and #88 (spreadsheet arithmetic disagreeing with `rowspec
  eval`);
- packaging: rowspec#47 (the sdist cannot declare kindkit, waiting on its
  publication).

Every other issue this file named on 2026-10-15 is closed, rowspec#141
merged (`gh api repos/kindspec/rowspec/issues/<n> --jq .state`).

The suite, the mutation gate and the case-tree convention come from kindkit,
pinned by commit. What stayed in rowspec is everything kindkit cannot be told.
The second implementation (`reference/rowspec_alt/`) is the load-bearing one —
written from `SPEC.md` alone and run against the same tree in CI. It claims
the `mdtbl` profile only; asked to run `--profile csv` it exits 2.

### kindkit — tagged v0.1.0, consumed by rowspec and blockspec, no open issues

    148 mutations, 148 caught, 0 survived, 0 broken   just mutants   (throwaway clone)
    220 passed                                         just test   (node on PATH)
    28 files clean                                     just check
    6 case(s) in its own kv tree                       just cases

All of these reproduce on 2026-10-15 at `6ebd80d`, through `just` in a fresh
clone with a private uv cache. `6ebd80d` (kindkit#26) is still `main`; nothing
has merged since 2026-10-08 (`gh pr list -R kindspec/kindkit --state all`). To
count tests, read pytest's own summary line.

**`v0.1.0` is older than `main`.** The tag peels to `bf716e3` (`git ls-remote
--tags https://github.com/kindspec/kindkit`), and `main` is 8 commits ahead
(`gh api repos/kindspec/kindkit/compare/v0.1.0...main --jq .ahead_by`).
kindkit is not on PyPI (`curl -s -o /dev/null -w '%{http_code}'
https://pypi.org/pypi/kindkit/json` prints 404).

**Two consumers, at two pins.** rowspec pins `8e21b55` and calls `kind.yml` at
it. blockspec pins `6ebd80d` in `pyproject.toml` and in `conformance.yml`'s
`KINDKIT_SHA`, and uses kindkit's case-tree validator, runner and mutation
gate (`grep -n kindkit pyproject.toml .github/workflows/conformance.yml
conformance/mutants.py`, run in blockspec); it does not call `kind.yml`.
`8e21b55` is 2 commits behind `6ebd80d` (`gh api
repos/kindspec/kindkit/compare/8e21b55...6ebd80d --jq .ahead_by`).

**kindkit's own gate edits tracked files.** `tools/mutation_gate.py` mutates
tracked files in place and restores them in a `finally`. A completed run is
clean; a killed one leaves a mutated tracked file. Run it in a throwaway
clone, and if you do kill one, **`git status` is the list**.

**The gate is Python-only** — `tokenize`, `ast`, `compile`. A kind whose
reference implementation is not Python gets the runner and not the gate.

### blockspec — the spike's binding verdict is FOUND; draft 0 has a SPEC.md, a case tree and a reference

**The spike.** blockspec#2 ran under three pre-registrations; the verdict that
binds is pre-registration 3's run 2, **FOUND** (`spike/LOG.md` §35):

    python3 -I -c "import json,collections,sys; v=json.load(open(sys.argv[1])); print(v['overall'], dict(collections.Counter(c['verdict'] for c in v['cells'].values())))" <verdict.json>

    spike/results/prereg2/verdict.json        INCONCLUSIVE {'NO VERDICT': 52, 'NOT FOUND': 4}
    spike/results/prereg3/verdict.json        INCONCLUSIVE {'NO VERDICT': 52, 'NOT FOUND': 4}
    spike/results/prereg3/run2/verdict.json   FOUND {'NO VERDICT': 16, 'FOUND': 35, 'NOT FOUND': 5}

- **Pre-registration 2** (blockspec#15 to #19, #26 to #28): its tiering was void, because
  the planted packets were answered wrongly, so every exporting cell is NO
  VERDICT and the verdict is INCONCLUSIVE (`LOG.md` §31).
- **Pre-registration 3** (`spike/PRE-REGISTRATION-3.md`, blockspec#22 to
  #30), a final re-tiering of the same records. Run 1 stopped when the host
  lost its network after 193 lines; three plants were untiered, so it is void
  and INCONCLUSIVE (`LOG.md` §32–§33). Both stay published unchanged.
- **The owner's ruling of 2026-10-14** (`LOG.md` §34, blockspec#31):
  pre-registration 3's tier-run runs once more, as run 2, which binds whatever
  it says, with no run 3. **It overrides frozen rules** — pre-registration 3
  §0 item 10, §6's run cap, §8's final-tiering rule and §11 — and it was made
  after run 1's answers and verdict were public. §34 quotes each rule it
  overrides and discloses two departures from §0 item 10's operating rules
  during run 2. `spike/ruling/prereg3_run2.py` runs the frozen harness
  unchanged apart from the run cap, the binding run and the aggregate's output
  path; `spike/harness3/` and the pre-registration are byte-identical.
- **Run 2** tiered all 488 packets, every plant answered as expected, and all
  13 new reproductions were byte-identical. Summed over the 35 FOUND cells,
  the cells' qualifying distinct units come to 432, 171 of them on an oracle
  DELETED target, which `ORACLE.md` §4 marks as weaker. Each cell counts its
  own distinct units, so a unit that qualifies in several cells counts once
  in each; `verdict.json` holds no unit ids, so the number of distinct units
  across cells cannot be read from it
  (`python3 -I -c "import json; c=json.load(open('spike/results/prereg3/run2/verdict.json'))['cells'].values(); print(sum(x['qualifying_distinct'] for x in c), sum(x['wrong_on_deleted'] for x in c))"`
  prints `432 171`).
- **Read it with its noise figures.** 413 of 483 real packets would qualify
  in run 2. Pre-registration 3 §2.6's rehearsal figures, all on synthetic
  packets, are 22 of 116, 0 of 117 and 23 of 117, and 139 of 486 on its own
  prompt, with q4 agreement in 68 of 119 between two runs; §2.6: "These
  figures compare runs. They are not accuracy". §2: the plants "do not
  measure its accuracy on real packets." Run 1's answers for 191 real packets
  are public and `LOG.md` §35 does not compare them with run 2's. The FOUND
  rests on one tiering run.
- **The write-up is the reproduction**, as pre-registration 2 §8 requires:
  `spike/results/prereg3/run2/reproduction.md`, generated from committed
  records by `spike/ruling/reproduction_run2.py`, gives each qualifying
  packet's commits and the exact `git show` or stock-git merge commands.

Under pre-registration 2 §8, FOUND means blockspec proceeds to #3, #4 and #5.
All three are closed, and **blockspec#2 was closed as completed on
2026-10-21** (`gh api repos/kindspec/blockspec/issues/2 --jq
'"\(.state) \(.closed_at) \(.state_reason)"'`).

**The adjudications** (`docs/adjudications/`), 0001 and 0002 each argued
from both sides, with the cases committed beside each:

- **0001, syntax** (blockspec#34, closing #3): **a pinned CommonMark 0.31.2
  block-level profile**, inline content opaque, decided on the owner's answer
  that a blockspec document must render and edit correctly in today's markdown
  tools. The one convention is D8 §7.2's region marker, `<!-- #name -->` and a
  `:begin`/`:end` pair. Setext headings, indented code, link reference
  definitions, raw HTML other than markers, duplicate names and conflict
  markers are refused. Its addendum fixes the marker line's exact pattern and
  heading slugs, github-slugger 2.0.0 character for character.
- **0002, the block** (blockspec#35, closing #4): a **block** is a top-level
  node (a list, a block quote and a table are one block each); anchoring
  resolves a **leaf** at any depth; a one-line marker names the next sibling in
  its container, a region pair the siblings between its markers; GFM pipe
  tables are in the profile with blank lines on both sides. Three addenda:
  frontmatter is allowed (line 1 `---`, line 2 not blank); a marker that names
  no node is `dangling-marker`, with a fixed order among the name refusals and
  `\n` as every leaf's line ending; and `ambiguous-table`, an eleventh refusal,
  for table-like shapes GitHub and the profile's readers draw differently.
- **0003, anchors and transclusion**: how comments, suggestions and
  transclusions anchor so that an anchor lands on the right text or is
  refused loudly. Not argued as two cases: the owner decided thirteen
  questions on 2026-10-16.
- **0004, fewer refusals of surviving text** (decided 2026-10-18): narrows
  two of 0003's rules after pre-registration 4 found its resolver refusing
  too much (below).

**`SPEC.md` is draft 0**, written up from 0001 to 0004; where it and an
adjudication disagree, the adjudication wins (`SPEC.md`'s status
paragraph).

**The anchor replays** (pre-registrations 4 and 5, `spike/`), each run on
real history with the harness in kindspec/research
`experiments/D8-anchor-replay/`:

- **Pre-registration 4: refusals too high.** 0003's resolver refused 17.0%
  (16.3% to 18.7%) of comments whose text survived five commits, against a
  5% bar (`docs/adjudications/0003-anchors/replay-verdict.md`). 0004
  answers it.
- **Pre-registration 5: pass**, on held-out repositories that played no
  part in choosing 0004: 2.9% (2.8% to 4.2%), and no comment at any gap
  `WRONG` (`docs/adjudications/0004-anchor-refusals/replay-verdict.md`).

**The case tree and the reference implementation**, at `3629226`
(blockspec#67's merge) on 2026-10-21, in a fresh clone with a private uv
cache:

    547 cases                       find conformance/cases -name expect.json | wc -l
    547 cases: 178 accept, 91 refuse, 278 anchor
    0 problem(s)                    just tree
    0 failures across 547           just conform
    123 killed, 0 survived          just mutants
    1 equivalent, 0 stale, 0 broken
    181 passed                      just test
    15 files clean                  just check

- **The tree came first.** blockspec#36 (closing #5) added 151 cases before
  any implementation existed, and blockspec#38 pinned fence, list, heading and
  frontmatter readings, for 237 (`git ls-tree -r --name-only <sha>
  conformance/cases | grep -c 'expect.json$'` at `926d7a1` and `ebfc86a`).
- **The reference** (blockspec#37) is `reference/blockspec/document.py`,
  standard library only, written against the tree with no case changed. The
  `ambiguous-table` code it needed in the schema reached `main` through
  blockspec#38 (`ebfc86a`), which merged first; #37's squash commit changes
  nothing under `conformance/cases/` (`git show --stat --format= <sha> --
  conformance/cases/case-body.schema.json` at `ebfc86a` and `d5355ab`).
- **The anchor resolver** is `reference/blockspec/anchor.py`. Its cases,
  under `conformance/cases/anchor/`, were written from `SPEC.md` by an
  author who had not read it, after it was written; 0004's cases the same
  way, after its resolver change (blockspec `README.md`).
- **Required checks: `conformance` and `reference`, strict**, ruleset 22723622
  (`gh api repos/kindspec/blockspec/rules/branches/main`). `conformance`
  validates the tree with kindkit's validator and checks the runner reports
  no verdict without an implementation; `reference` runs `just check`,
  `just conform` and `just test`. Both are `success` on `3629226` (`gh api
  repos/kindspec/blockspec/commits/3629226/check-runs`).
- **The mutation gate is not in CI**, by blockspec's `AGENTS.md`, Status: a
  survivor is a hole for the case author, not a reference bug. Run it by hand.
- **There is no second implementation.** The adjudications decide draft 0,
  `SPEC.md` writes it up, and the tree encodes it.

**blockspec's own documents match this.** blockspec#39, which brought
`README.md`, `spike/README.md`, `AGENTS.md` and `DESIGN-BRIEF.md` into line
with the verdict and draft 0, merged on 2026-10-15 (`gh api
repos/kindspec/blockspec/pulls/39 --jq .merged_at`).

**One open issue**, blockspec#62, the questions `SPEC.md` leaves open around
U+0000; its latest comment records the owner's ruling on item 4 and says
item 5 stays open (`gh api repos/kindspec/blockspec/issues/62/comments`;
`gh issue list -R kindspec/blockspec --state open`).

**`spike/README.md` "Read these before believing anything here"** still
applies to any spike result: `LOG.md` §9 retracts the claim that the defect
needs both merge legs, and `LOG.md` §6.2 shows the oracle returning
`SURVIVED` with full confidence where the truth is undecidable.

### research — the evidence base, reproducible

Not a specification. It is the design record the briefs cite. **No open
issues** (`gh issue list -R kindspec/research --state open` prints nothing).
Two pull requests merged on 2026-10-14 as evidence for blockspec#4:
research#17, `experiments/D8-block-definitions/`, D8's within-file uniqueness
under eleven candidate block definitions; and research#18, which node stage 1
of a quote anchor resolves. The D8 harnesses refuse a corpus off its pin
(research#16). From 2026-10-17 to 2026-10-20, research#19 to #25 added
`experiments/D8-anchor-replay/`, which replays real history against
blockspec's anchor resolver, and published the runs of blockspec's
pre-registrations 4 and 5 (`gh pr list -R kindspec/research --state merged
--limit 12`).

**The corpora are not in the repository.** `CORPORA.md` names each one with its
source and pin. A fresh machine has to clone them; see §3.

### nodespec — spec draft 0, a reference checker and its cases; the spike is closed

`spike/mermaid/` (nodespec#2 to #10) asked whether stock git merges a Mermaid
flowchart silently wrong. Both of its questions ended **NO VERDICT**
(`spike/mermaid/LOG.md` §15). Real merged history put identity at risk once,
and git refused that merge; structure decided 9 cases against a floor of 60.
The spike is closed and identity is parked (`README.md`, nodespec#10). The
bound `aggregate` was never run: the frozen aggregator raises `TypeError` on
the real results, and the verdict was computed by the owner's ruling with the
frozen `aggregate.verdict` on the non-null-key cases (`LOG.md` §15,
`ruling/redfirst.py`).

**Since then** (re-read on 2026-10-21 with `gh api`, `main` at `9b7c89b`):
`SPEC.md` is draft 0, written from `docs/adjudications/0001-mermaid-profile.md`
(nodespec#13, #14). `reference/nodespec/` is a checker for it, and
`conformance/` holds its cases (nodespec#15, titled "301 cases"; 322
`expect.json` files under `conformance/` today, `gh api
"repos/kindspec/nodespec/git/trees/main?recursive=1"`). One workflow,
`.github/workflows/check.yml`, runs a Python 3.11 and 3.12 matrix and a
`check` aggregator, and the ruleset requires `check`, strict. No open issues
(`gh issue list -R kindspec/nodespec --state open`).

**Its existence criterion is met.** `existence/RESULT.md` records three
constructed cases that meet `existence/CRITERION.md`, fixed before they
ran: stock git merges a Mermaid flowchart with no conflict into a file
Mermaid parses and that is wrong about which nodes exist. **No reading in
`SPEC.md` is provisional**: §12 lists the readings the owner settled on
2026-10-20, the last three through nodespec#22.

### .github — the org contract, this file, the org page, the audit

`AGENTS.md`, `STATE.md`, `profile/README.md`, the default issue forms, and
`scripts/check_required_checks.py`.

**The required-checks audit exits 0 on the org** with the script as .github#28
leaves it. On 2026-10-21:

    $ python3 -I scripts/check_required_checks.py --public-only
    2 private repositories skipped (--public-only)
    6 repositories, 9 workflows, 12 pull request jobs, 10 required checks: 0 finding(s), 0 not evaluated

The same day, `main` at `18d47b6` gave `2 finding(s), 4 not evaluated`, exit 1:
CONDITIONAL on nodespec's `check-all` and rowspec's `conformance-all`, and
four refusals over those repositories' two Python matrix jobs. Each `-all` job
reports the matrix under the required name with `if: always()`, which cannot
be skipped, and one step that tests `needs.<matrix>.result` = `success`. Each
matrix reports only `<name> (<version>)` contexts, as `check (3.11)` and
`conformance (3.12)` do on each repository's `main` (`gh api
repos/kindspec/<repo>/commits/<sha>/check-runs`), so neither can produce a
required context. Both matrix jobs are in `ALLOW`, gated through their
aggregator. On 2026-10-15, at `cb04c2c`, the audit gave `6 repositories, 8
workflows, 9 pull request jobs, 9 required checks: 0 finding(s)`; the ninth
workflow is nodespec's `check.yml`, and the tenth check its required `check`.

**It runs daily; the 2026-10-20 run was its first scheduled failure.**
`.github/workflows/required-checks-audit.yml` runs the line above on cron
`17 6 * * *` and by hand. The 12 scheduled runs from 2026-10-08 to 2026-10-19
concluded `success`, run 39415720347 on 2026-10-20 concluded `failure`, and
run 39594320069 on 2026-10-21, at `98fecba`, concluded `success` (`gh api
"repos/kindspec/.github/actions/workflows/required-checks-audit.yml/runs?per_page=100"
--jq '.workflow_runs[]|"\(.id) \(.event) \(.conclusion) \(.created_at)"'`).
The workflow runs the audit only: the script's self-test and its mutation
sweep (`python3 -I scripts/check_required_checks.py --selftest`;
`scripts/sweep_check_required_checks.py`) run in no CI, so run both by hand
when changing the script.

**What it reads.** A job that calls a reusable workflow expands into one
`<caller> / <called job>` context per called job, read at its pinned ref
(.github#15). A required context with a second producer is a DUPLICATE,
exit 1: a `push` on some branch other than the default, in the same workflow
(.github#16) or another (.github#18), or a second pull request producer on
`pull_request` or `pull_request_target`, reported whether or not `ALLOW`
names either job (.github#20), or on `pull_request_review`, or a
`deployment` or `deployment_status` job, or a second job of the same workflow
(.github#22). A required check whose only producers are
`pull_request_target` jobs is TARGET-ONLY, exit 1, unless `TARGET_OK` accepts
it with a reason. One that only `pull_request_review` produces is TRIGGER,
exit 1. A filter or a job name it cannot settle is refused, exit 2, and so is
a required check that only deployment jobs produce, or that only an unread
deployment job could. A job-level `if:` of exactly `always()` is not
CONDITIONAL when the job has needs and, for each, a one-line `run:` step that
compares `${{ needs.<n>.result }}` for equality with `success`. A matrix job
with a literal name reports only `<name> (<values>)`, so it is refused only
when a required context has that form; otherwise it is UNGATED unless `ALLOW`
names it and a required job of that kind needs it.

`pull_request_target` check runs carry the pull request's head sha:
python/cpython run 25066296099 (fork PR 149109), electron/electron run
37748122900 on PR 54550's head `a965781`, and react/react run 37730121633 on
fork PR 37788's head `7af445b`. GitHub's "Troubleshooting required status
checks" (github/docs
`content/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks.md`,
lines 55–64 at `60f9f34`) lists `push`, `pull_request`, `pull_request_review`,
`pull_request_target`, `deployment` and `deployment_status` as events whose
checks count. That a ruleset accepts a `pull_request_target` check is the
documentation's word; no kindspec ruleset has been watched doing it.

**The other events on that list, and two jobs of one workflow** (.github#22).
Read-only checks on 2026-10-20, with `gh api repos/<o>/<r>/actions/runs/<id>`,
`…/runs/<id>/jobs`, `commits/<sha>/check-runs`, `deployments?sha=<sha>`, and
a GraphQL query of the pull request's `statusCheckRollup`:

    run                                              event                pull request head
    vectordotdev/vector 39523324096                  pull_request_review  PR 26759, 84aba9b
    Expensify/App 39523875193                        pull_request_review  fork PR 102135, d52f209
    oaknational/oak-ai-lesson-assistant 39512415827  deployment_status    PR 1157, 97881e5
    timvir/timvir 39506542194                        deployment_status    PR 4043, 207ee29
    kube-HPC/hkube 39365408319                       deployment           PR 2500, 43c5a07

Each run's check runs are listed on that head and in the pull request's rollup
with the run's event. Expensify's head carries `checklist` from nine
`pull_request_review` runs, one per review, so that event reports on a head
only once someone reviews it. Each deployment run's `head_sha` is the sha of a
deployment created for that head (by `vercel[bot]` or `hkube-ci`), so those
events report on a head only when something deploys it. Hence:

- `pull_request_review` is a pull request event: a second producer is a
  DUPLICATE, an unrequired job is UNGATED, and a required check it alone
  produces is TRIGGER, not ORPHANED. A branch or path filter on it is refused,
  exit 2.
- A `deployment` or `deployment_status` job with a required context is a
  DUPLICATE. A required check that only such jobs produce is refused, exit 2:
  whether every head is deployed is not in any workflow file.
- Two jobs of one workflow with the same required context are a DUPLICATE.

On 2026-10-20 no kindspec workflow runs on those events, and the audit's
output on that day's snapshot is the same before and after the change (read
from each public repository's `.github/workflows/` on `main`).

#### Security settings, org-wide

**Re-checked on 2026-10-21**, by reading configuration back:

- `gh api repos/kindspec/<repo> --jq .security_and_analysis` shows secret
  scanning and push protection `enabled` on all six repositories;
- `gh api orgs/kindspec` shows two-factor required and both new-repository
  defaults `true`;
- `gh api repos/kindspec/<repo>/rulesets/<id>` shows every ruleset `active`
  with an empty bypass list; rowspec, kindkit, blockspec and nodespec add
  `required_status_checks`, strict;
- `squash_merge_commit_title` is `PR_TITLE` and `squash_merge_commit_message`
  `PR_BODY` on all six; `allow_auto_merge` is `false` on all six.

`AGENTS.md` §3.1's table matches the required checks
(`gh api repos/kindspec/<repo>/rules/branches/main`). Three rulesets have a
recorded rejection of a push to `main`, each still returned with `result`
`fail` by `gh api repos/kindspec/<repo>/rulesets/rule-suites/<id>`: `.github`
4014197203, rowspec 4014189520 and nodespec 4014318589, all on 2026-09-10.
research, kindkit and blockspec have none on record, so they remain
configured, not verified. The `rule-suites` listing cannot settle that: it
reaches back about a month, so on 2026-10-21 it returns no failure even for
the three rejections above.

A push holding a generated AWS key pair was refused with `GH013` on each of the
six (.github#4, closed). A never-issued `ghp_` token is *accepted* — it is not
a secret to the scanner — so test with a pattern-matched provider.

**rowspec's `pypi` environment deploys only from `v*` tags, and has been
watched refusing.** Its only deployment policy is `tag v*` (`gh api
repos/kindspec/rowspec/environments/pypi/deployment-branch-policies`). Release
run 37720734896, a `workflow_dispatch` on `main`, failed `publish` with
"Branch "main" is not allowed to deploy to pypi due to environment protection
rules". rowspec#55 is closed on that.

---

## 2. What comes next

### Owner decisions

Settled.

- **blockspec#2's binding verdict is pre-registration 3's run 2, FOUND,** under
  the owner's ruling of 2026-10-14 (`spike/LOG.md` §34). There is no run 3.
- **blockspec's syntax and block model are decided** (adjudications 0001 and
  0002, with their addenda). Reversing either is an escalation (`AGENTS.md`
  §7); each document's *What would reverse it* says on what grounds.
- **blockspec's anchor design is decided**: adjudication 0003 (2026-10-16),
  amended by 0004 (2026-10-18), whose held-out replay passed (§1).
- **nodespec's mermaid spike is closed and identity is parked** (nodespec
  `README.md`). Its existence criterion is met, and the owner settled the
  readings `SPEC.md` §12 lists (§1).
- **The CSV profile's readings in SPEC.md §13 are decided**, and so are the
  spec rulings of rowspec#110, #115, #116, #117 and #118.
- **kindkit goes to PyPI once its contracts have a second consumer.**
  blockspec now consumes the validator, the runner and the gate (§1). It is
  still unpublished; publishing it is the owner's call.
- **A rowspec release is tagged only with the owner's approval**, because a
  `v*` tag is what publishes to PyPI. 0.4.0 carried the breaking change for
  implementations (§9 identifiers). Whether and when `main`'s `[Unreleased]`
  is released is the owner's call.

Done since 2026-10-15: blockspec#39 merged and blockspec#2 is closed (§1);
rowspec's reference defects and spec questions filed 2026-10-14/15
(rowspec#112, #113, #130–#135, #140, #142–#145) are closed and rowspec#141
merged; and identifiers end to end (rowspec#99, #101, #103) are closed.

In order:

1. **blockspec — draft 0 beyond one implementation.** `SPEC.md` is written,
   and there is no second implementation; rowspec's history is that the
   second implementation is what tests whether the spec defines the format.
2. **kindkit — publication**, if the owner chooses it (above); rowspec#47
   waits on it.

Also open, in no decided order: blockspec#62 item 5 (§1), and rowspec#272
and the xlsx export issues rowspec#35, #83 and #88. Each fix needs a case
written by someone who did not write the fix (`AGENTS.md` §2.1, §5).

Open issues carry acceptance criteria and a red-before-green requirement. List
them per repository rather than trusting a count written here:

    gh issue list -R kindspec/<repo> --state open --limit 200

Issues closed since 2026-10-09 (`gh issue list -R kindspec/<repo> --state
closed --limit 300 --json number,closedAt --jq
'[.[]|select(.closedAt>="2026-10-09")|.number]'`, on 2026-10-21):

- rowspec: 82 issues, too many to list here; run the command;
- blockspec: blockspec#2, #3, #4, #5, #21, #42, #49, #64 and #66;
- .github: .github#22;
- kindkit, research and nodespec: none.

---

## 3. Setting up on a fresh machine

**Toolchain.** `git`, `just`, `python3` 3.11+, `uv` for rowspec, kindkit,
blockspec and nodespec, `ruff` and `pytest` through `uv`, and `pre-commit`. A real `git`
binary is a hard dependency of every conformance suite, because the central
claim is about what stock git does. rowspec's `just test-libreoffice` needs
`soffice` on `PATH`.

**First command in rowspec, kindkit, blockspec and nodespec is `uv sync`** (or `just
setup`). It creates `.venv`, which is gitignored. `uv sync` needs network
reach to `github.com`: rowspec and blockspec take `kindkit` as a git
dependency, so an offline sync fails there. Run it somewhere `~/.cache/uv` is
writable; see the sandbox note at the end of this section.

**blockspec's spike harness is pure stdlib, run with `python3` directly**; the
case tree check (`just tree`) is too. Everything else in blockspec goes
through `uv`.

**`node` is required by kindkit's test suite**, not optionally: the case-tree
validator translates Python regex semantics to ECMA-262 and the differential test
checks the translation against a real engine. Without `node` on `PATH` that test
skips, and a mutation exists specifically so a skip fails the gate.

**kindkit's §1 figures need bytecode writing enabled.** Three of its tests and
one of its mutants exercise stale `.pyc` handling. With
`PYTHONDONTWRITEBYTECODE=1` in the environment, `uv run pytest -q` at
`6ebd80d` gives `3 failed, 217 passed`, and `just mutants` gives `148
mutations, 147 caught, 1 survived, 0 broken` (measured 2026-10-15). Unset it
before measuring. blockspec's
`tools/slugger/ranges.mjs` also needs node, only to regenerate the slug table.

**Corpora.** They live outside the repositories and are gitignored. **Clone the
pins in `research/design-findings/D8-identity.md` §3. They produce all four
committed artifacts, byte for byte.**

| corpus | pin | source |
|---|---|---|
| `rust-book` | `1500248d8f230566e4ec9f27fcbb8fe9e2898ab1` | `github.com/rust-lang/book` |
| `obsidian-help` | `327a782e90481268361b5ccccdb0c224b2b13fe6` | `github.com/obsidianmd/obsidian-help` |
| `cmspec` | `3da939428d80f146f270cd1765e4ba462e96bb1b` | `github.com/commonmark/commonmark-spec` |

**`blockspec/spike/harness/corpora.json` pins different commits on purpose, and
they are not an alternative set to reproduce research with.** It pins
`obsidian-help` at `a3985b58` and `rust-book` at `917544888a55` to reconstruct
an *earlier, uncommitted* pass. Its control arm therefore prints `anchors=384`
where `results-anchor3.txt` prints `343`, and both are right about their own
tree. D8 §3.2: *"The 384 line belongs to `a3985b58` alone."*

**Name the directories `rust-book`, `obsidian-help` and `cmspec`.**
`e4_uniqueness.py` and `anchor_eval3.py` hardcode those paths under
`corpora/`, **relative to the process working directory** — so invoke them
from that parent directory by absolute script path. Get either wrong and both
harnesses exit 1 naming the directory git could not enter (research#11).

**The D8 harnesses refuse a corpus that is off its pin** (research#16).
`experiments/D8-identity/corpus_pin.py` holds the three pins above, and
`D8_ALLOW_UNPINNED=1` overrides it for a run meant for another tree, such as
blockspec's `a3985b58` control arm, with a warning.

`run_control.sh` takes `CORPORA` and `D8_DIR` as **environment variables**, not
flags. `--d8-dir` is `prose_merge.py`'s flag.

**blockspec#2's corpora are seven arms over six repositories**, in
pre-registration 2 §6.2: `rust-book`, `obsidian-help` and `cmspec` at D8 §3's
pins above, and `kubernetes/website` (as `k8s-en` and `k8s-l10n`), `cncf/toc`
and `github/site-policy` at the first registration's §5.1 pins. blockspec's
`NOTICE` lists them with their licences (blockspec#33).

**If a session is sandboxed**, check that `~/.cache/uv` is writable before
reaching for `just`. A read-only cache makes every `uv run` recipe fail with
`OSError 30` *before the recipe body runs*, which reads as a broken repository
and is not one. Once a `.venv` exists, call `./.venv/bin/...` directly and every
figure in §1 reproduces; but `uv sync` is itself that entry point, so sync
first from a session that can. Do not redirect `UV_CACHE_DIR` into scratch to
get around a read-only cache — an empty cache in a sandboxed session cannot
populate itself, and it hides the fault from the next session.

**rowspec's "2 skipped" depends on `openpyxl` being absent**, not on a flag.
`just test` runs `uv run --exact`, which removes `openpyxl` even if you
installed the extra, so its figure does not move. A bare `./.venv/bin/python
-m pytest` in a venv that has the extra changes it, with nothing in §1 to
explain why.

---

## 4. Traps that have already cost time

**`anchors=384` and `anchors=343` are the same arm on two different trees, and
the committed artifact is 343.** `results-anchor3.txt:12` prints 343, produced at
research §3's pins. `384` comes from `obsidian-help` at `a3985b58`.
`blockspec/spike/results/corpus-drift.txt` tabulates both. **Always name the
SHA and say which artifact you are reproducing.**

**Do not use `git rev-list --count` to decide which pin is right.** D8 §1's
header states 6,286 / 2,623 / 1,848 and those counts match `a3985b58` and
`917544888a55` — the *earlier* clone, not the one §3 pins. That count was read
twice as support for a wrong hypothesis, and both times would have written a
false claim into research (research#9). A check that returns the same answer
whichever hypothesis is true cannot choose between them. `diff` against the
committed artifact is the check that discriminates.

**A squash merge discards branch commit messages.** Every repository here has
`squash_merge_commit_message = PR_BODY`, so the PR description becomes the commit
and anything recorded only in a commit message is destroyed on merge. Put what
must survive in a file or in the PR body.

**The squash commit's subject is the pull request's title**
(`squash_merge_commit_title = PR_TITLE` on all six). A title written while the
work was in progress lands on `main` as it stands, and no force-push can take
it back: blockspec's `0dd32dd` is a merged harness whose subject still ends
"(do not merge)". **Read the title, and update it, before merging.**

**A GitHub scheduled workflow can run hours after its cron slot.** The daily
audit's cron is `17 6 * * *`; its scheduled runs from 2026-10-08 to 2026-10-14
were created between 11:48 and 15:19 UTC (`gh api
"repos/kindspec/.github/actions/workflows/required-checks-audit.yml/runs"
--jq '.workflow_runs[]|"\(.event) \(.created_at)"'`). An absent scheduled run
is not evidence that the workflow is broken until well past its slot; read the
run list and the workflow's `state`, and dispatch it by hand if the answer is
needed now.

**Never stop a process you did not start.** Some runs here cannot be repeated.
A bound pre-registration run is marked executed once it opens its input, and a
killed run still uses it up (blockspec `spike/harness/p2/binding.py`, its
docstring). Pre-registration 2's seven scoring runs took from
2026-10-08T17:13Z to 2026-10-09T11:20Z (`spike/LOG.md` §25). A background job
that looks idle or stuck may be one of them. Ask whoever started it.

**A bound run depends on the host's network.** Pre-registration 3's run 1 ended
when the host lost Wi-Fi, after 193 lines, and under the frozen rules that was
binding and void (`spike/LOG.md` §32). Check the network is stable before
starting a bound run that cannot be repeated.

**A stacked pull request whose base was squash-merged will not update cleanly.**
The squash commit on `main` holds the base branch's changes under a new hash,
so merging `main` into the stacked branch replays the same edits twice and
conflicts. The org forbids force-push, so a rebase is not available. Merge
`main` and resolve each conflict by hand, taking `main`'s side for whatever the
base already landed. Better, branch the second change from `main` once the
first has merged.

**Strict mode plus several pull requests that touch the same file means serial
conflicts.** Each merge makes every other open pull request out of date, and
where they all edit one region, typically `CHANGELOG.md`'s `[Unreleased]`, each
also conflicts with the one just merged. rowspec merged 27 pull requests on
2026-10-14/15 this way (`gh pr list -R kindspec/rowspec --state merged --search
'merged:2026-10-14..2026-10-15' --limit 200 --json number --jq length`). Land them one
at a time, merging `main` and resolving before each, and expect to rerun CI for
every one.

**A required status check is matched by job name, and a name that never reports
blocks the merge forever.** Renaming a job needs the ruleset edited *first*,
because the change that renames it is itself the change that cannot merge.
Requiring both names during the transition blocks everything.

**A pull request that adds a code its own tree has no case for is red until
the case lands.** blockspec#37 added `ambiguous-table` to the schema and
`check_tree.py` requires a refusal case for every code, so its `conformance`
job was red until blockspec#38 merged; #38 merged first. Order such pairs
deliberately rather than weakening the check.

**`git push --dry-run` does not evaluate server-side rules.** It reports success
against a branch that would reject the real push. To check a ruleset, read
`gh api repos/OWNER/REPO/rulesets/rule-suites`, which logs real attempts with
pass/fail, rather than the configuration.

**A same-size edit within the same second reuses the previous `.pyc`.** CPython
invalidates on `(mtime in whole seconds, size)`, so two mutations of one file can
have the second execute the first's bytecode. kindkit dates every scratch write
with its own mtime second (kindkit#23) and purges what it can see (kindkit#14).
A gate of your own that writes a file and re-imports it has the same problem;
kindkit's README, "What a probe has to get right", lists what the stamp does not
reach.

**`awk $5` on the uniqueness output is magnitude-dependent.** Under `{:4.1f}` a
one-digit percentage is padded to `" 0.6"`, so `( 0.6%)` splits into two tokens
and a two-digit one does not. Parse with an anchored regex.

**The spike harness's default `--d8-dir` assumes a layout.** It looks for
`$HOME/research/experiments/D8-identity`; pass `--d8-dir` explicitly.

**Editing a file inside a uv-managed `.venv` edits it for every venv on the
machine.** uv installs by hard link from `~/.cache/uv`, so a write to an
installed file writes through to the cache entry. On 2026-10-07 that corrupted
a cached kindkit, and a fresh clone of rowspec `main` then failed `just
mutants` (rowspec#57); repaired with `uv cache clean kindkit`. `stat -c %h
<file>` above 1 means a hard link. For an experiment that edits installed code,
use `UV_CACHE_DIR=<scratch dir> UV_LINK_MODE=copy uv sync`.

**`gh issue view` and a plain `gh pr view` fail with gh 2.46.0**, exiting 1
with a GraphQL error about Projects (classic) — a property of that gh version,
not of the repositories (re-checked 2026-10-15). `gh pr view <n> --json
<fields>` works. Otherwise use the REST API: `gh api -X PATCH
repos/kindspec/<repo>/pulls/<n> -F body=@file` to edit a body, `gh api
repos/kindspec/<repo>/issues/<n>` and `.../comments` to read an issue.

**GitHub matches a closing keyword even when the sentence negates it.**
kindkit#14's body had the heading `## Not done: why this does not close #11`,
and merging it closed kindkit#11. Never write `close`, `closes`, `fix`, `fixes`,
`resolve` or `resolves` followed by `#N` in a PR body or a commit message unless
that issue should close — not even negated. Write `Refs #N`, and run

    gh api graphql -f query='{repository(owner:"kindspec",name:"<repo>"){pullRequest(number:<n>){closingIssuesReferences(first:10){nodes{number}}}}}'

on every pull request you open.

---

## 5. What is decided, and must not be re-litigated

- **§3, §4 and §6 of blockspec's first pre-registration, pre-registration 2 as
  a whole, and pre-registration 3.** The sanctioned route past a frozen
  pre-registration is superseding, never an edit. The owner's ruling of
  2026-10-14 (`spike/LOG.md` §34) overrode four of pre-registration 3's frozen
  rules for one rerun; its run 2 binds, and there is no run 3.
- **blockspec draft 0's syntax and block model**: adjudications 0001 and 0002,
  with their addenda.
- **blockspec's anchor design**: adjudication 0003 (owner, 2026-10-16), with
  its addenda, as amended by 0004 (owner, 2026-10-18), which pre-registration
  5 passed. Changing either is a new adjudication, never an edit.
- **A fresh agent behind an information barrier counts as independent.** For
  suite authoring, `AGENTS.md` §2.1 says what the barrier is: an exported
  directory holding only the permitted files and no `.git`, not a worktree.
  The same standard is used for blind judgement under a pre-registration;
  that use is a decision recorded here, not in `AGENTS.md`. What each was
  given is logged in the repository it works on.
- **Identity per kind.** Opaque row ids for rowspec, no minted ids for prose,
  named rather than positional for nodes. The prose decision rests on
  `research/design-findings/D8-identity.md` §3.3 — 100.0% within-file
  uniqueness for `rust-book` prose at ≥40 characters and 99.4% for
  `obsidian-help`. nodespec's identity question is parked, not reversed.
- **Correctness may not depend on a merge driver, a clean/smudge filter or a
  hook.** None of them travel, and a bare repository does not consult
  `.gitattributes` at all.
- **One model, several grammars.** Do not reuse one kind's syntax for another.
- **The per-directory licence split**, and why: fixtures are CC0 with no prose
  attached so they can be vendored into an implementation in any language.
- **Depend on kindkit rather than vendoring it.** Vendoring reintroduces the
  duplicated-implementation drift the kit exists to prevent. A kind pins it by
  commit.

---

## 6. The transferable result

Repeatedly, across mechanisms that look unrelated, a check reported a pass over
something it had never evaluated. The list below is what has been recorded; it is
the only counted list, because `AGENTS.md` §2.2 points here rather than
carrying its own total:

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
  pip error included — withdrawn before it ever ran (rowspec#51)
- a mutant whose run skipped cases still scored equivalent, because the gate
  never compared what ran against the baseline (kindkit#16)
- a CI suite step passing a runner that had read a different tree with the
  same case names, or fallen back to its default tree, because it compared
  case names and never the root they were read from (kindkit#24)
- a CI mutation step accepting any exit 0, so `true` passed as a mutation gate
  that had run nothing (kindkit#24)
- a required-checks audit reporting 0 findings for a required check produced
  only by `merge_group` or a `pull_request` filtered to another branch, neither
  of which ever reports on the pull request it gates (.github#10; reproduced
  with `--load` against that pull request's first commit, `0970870`)
- the same audit reporting 0 findings while kindkit's required `check` and
  `kind / conformance` ran twice on a pull request head, once from a bare
  `push` and once from `pull_request`, because it read only the
  `pull_request` trigger (.github#16; on kindkit#25's head `79d194a`)
- the same audit, with that fixed, still reporting 0 findings when the second
  producer was a `push` job of the same name in a different workflow
  (.github#18)
- the same audit, with that fixed, still reporting 0 findings when the second
  producer was a job of the same name in another workflow on `pull_request` or
  `pull_request_target` (.github#20)
- the same audit, with that fixed, still reporting 0 findings when the second
  producer ran on `pull_request_review`, `deployment` or `deployment_status`,
  or was another job of the same workflow, and ORPHANED for a required check
  that only `pull_request_review` produced (.github#22)
- the change that fixed it, before merge, reporting ORPHANED, exit 1, rather
  than refusing, for a required check that only a deployment matrix job, an
  expression-named one or one calling an unread workflow could produce
  (.github#27)
- `corpus_check.py`, a green CI step in rowspec that never opened a `.mdtbl`
  file and printed `0 identified artifact(s), 0 duplicate id(s)` on rowspec's
  own tree (rowspec#68)
- the audit's `push` DUPLICATE rule, before merge, reporting 0 findings for
  `branches-ignore: ['**', '!feature/**']` and for `push: branches: []`; both
  are now refused, exit 2 (.github#17, at `f111068`)
- the audit's pull request DUPLICATE rule, before merge, exiting 0 when `ALLOW`
  named the first producer, because the pairs depended on `ALLOW` (.github#21)
- the same change, one round later, letting `ALLOW` accept a TARGET-ONLY
  required job by skipping every check on that job (.github#21)
- the audit on `main` reading `types: []` as no `types` filter at all, because
  an empty list is false (.github#21; its self-test grafted onto `main` gives
  `got [] exit 0`)
- 98 of rowspec's 116 refusing `parse` cases asserting `refusal_contains: ""`,
  which passed on a refusal for any reason (rowspec#61, fixed by rowspec#87;
  `CHANGELOG.md` `[0.4.0]`)

The pattern is not about tables, and it is why `AGENTS.md` §2.2 is mechanical
rather than advisory: break the thing a check checks, watch it go red, put it
back. A check whose red state nobody has observed is not a check.

One refinement deliberately not promoted to the contract: a check has a
**property**, a **detector**, and the **detector's inputs**, and §2.2 as
written exercises only the detector, against the one mutation whoever wrote it
happened to choose. Arming a check validates one layer and tends to expose the
next. The regress ends not by adding another check but by making the failure
structurally impossible — deriving a count from a set size rather than
accumulating it inside the loop that can skip. That is n=1 and it stays in
`blockspec/spike/LOG.md` §5.6 until it recurs somewhere the contract would bind.
