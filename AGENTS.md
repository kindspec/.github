# AGENTS.md — the kindspec agent contract

The org-wide contract for AI coding agents working in any
[kindspec](https://github.com/kindspec) repository.

Each repository also carries its own `AGENTS.md` with constraints specific to it.
**Where they conflict, the repository's file wins** — this file is the floor, not
the ceiling.

---

## 1. What this org is

A specification and conformance suite per artifact kind. Knowledge artifacts —
tables, documents, canvases — are edited by several people over years, and
version control is where that happens.

    rowspec     rows    opaque row ids                  draft 0, implemented
    blockspec   blocks  deliberately no minted ids      design pass
    nodespec    nodes   named, not positional           not started

Each kind is named after its **unit of identity**, because identity is the hard
part of every one of them.

**The conformance suite is the deliverable.** The specification exists so the
suite has something to check. The reference implementation exists so the suite
has something to run against. If you are choosing what to spend effort on and
the answer is not obvious, it is the suite.

The design record — every measurement these specs cite — is
[kindspec/research](https://github.com/kindspec/research). Cite it by path and
commit, not by recollection.

---

## 2. The two standing rules

These are not style preferences. Each was learned by violating it, repeatedly,
and each has a mechanical enforcement below.

### 2.1 The suite is not written by whoever writes the implementation

A standing role, not a review step. Three separate times an enumerator checking
their own work reported full coverage, and an adversary then found silently
wrong cases in the same code.

**Enforcement is the filesystem, not the prompt.** An agent authoring
conformance cases works in a git worktree that does not contain the
implementation at all. It cannot read `reference/` because `reference/` is not
there. An agent that finds itself able to read the implementation it is writing
cases against must stop and say so rather than proceed carefully.

### 2.2 A check that cannot fail must never report a pass

This project has now reproduced that failure ten times in its own tooling: a
runner that walked an empty directory and printed `0 failures` over 226 unopened
cases; a mutation gate that disarmed itself on a reformat; a canonicaliser that
scored 129/131 while being the identity function; a differential harness whose
injected defect silently stopped applying.

**Every check you add must be shown to fail.** Break the thing it checks, watch
it go red, put it back. A check whose red state you have not personally observed
is not a check. This is the most transferable thing here and it has nothing to
do with tables.

---

## 3. How work lands

**Branch, PR, review, merge.** No direct commits to `main` on a repository that
has a conformance suite.

A PR merges when **both** hold:

1. CI is green — every workflow, not the one you were watching.
2. An **independent reviewer agent** has reported and its findings are
   addressed. Independent means: it did not write the code, and it is given the
   diff and the repository's rules but not the authoring conversation.

### 3.1 What is enforced, and what is not

Clause 1 is enforced by a repository ruleset on the default branch of **all six**
kindspec repositories. Direct pushes to `main` are rejected, history cannot be
rewritten or the branch deleted, and only squash merges are allowed.

    repo        required checks                                            strict
    rowspec     conformance, xlsx-extra,                                   yes
                passes-on-a-good-tree, fails-on-a-broken-total
    kindkit     check                                                      yes
    blockspec   none — no workflows of its own yet                         n/a
    nodespec    none — no workflows of its own yet                         n/a
    research    none — no workflows of its own yet                         n/a
    .github     none — no workflows of its own yet                         n/a

**"Strict" — branch must be up to date with `main` before merging — applies only
to `rowspec` and `kindkit`.** It is a parameter *of* the required-checks rule, so
a repository with no required checks has no up-to-date requirement either. Say
"two of six", not "all", and add it when those repositories gain workflows.

**CodeQL runs on every repository** through GitHub's default setup, and is
deliberately **not** required. Its check names are generated from language
detection — `blockspec` currently detects no language and produces no `Analyze`
run at all — so requiring them would be a rule whose contexts move underneath it,
and would deadlock `blockspec` outright. Clause 1 says *every* workflow: for
CodeQL that means read it, because the gate will not.

Nobody bypasses: the bypass list is empty on all six, and that includes org
owners. A rule that its author can step around is the thing this project exists
not to ship.

**`require_extra_approval_for_unattributed_changes` is off, deliberately.**
GitHub defaults it on, and it adds one to the approval count for changes not
attributed to a person — the agent case, which is most of this org's work. With
one member, no self-approval, and an empty bypass list, that turns an
agent-authored pull request into one nobody can merge and nobody can override.
Revisit it when there is a second person to approve.

**Clause 2 is not enforced by anything.** No machine checks that a reviewer
agent ran, and the ruleset requires zero approving reviews — because the review
is performed by an agent, which cannot approve a GitHub pull request. So the
adversarial discipline, which is the more important of the two clauses, is
honour-system and will stay that way until something can attest to it. Say so
rather than implying the green tick covers it.

### 3.2 Three ways this gate can quietly stop working

Each is the pattern in §2.2, one layer up in the infrastructure.

- **A required check is matched by job name, and a name that never reports
  blocks the merge forever.** This is the opposite of what it sounds like: the
  requirement does not quietly lapse, it pins the pull request at *"Expected —
  waiting for status to be reported"* and nothing can move it. Renaming
  `conformance` runs the renamed job on that branch, leaves the required
  `conformance` context unreported, and makes that pull request unmergeable —
  by anyone, with no bypass. **The ruleset must be edited before the rename
  lands, not in the same change**, because the change that renames the job is
  itself the change that cannot merge.
- **A new workflow is not required by default.** Adding CI to a repository does
  not add it to the ruleset. A repository can gain a suite that never gates a
  merge, which is exactly the shape of a check nobody is running.
- **A path-filtered workflow never reports on an unrelated PR.** Requiring one
  blocks every merge that does not touch its paths, forever. No kindspec
  workflow is path-filtered today; keep it that way, or do not require it.

**Verify a rule by watching it reject, not by reading its configuration.**
`git push --dry-run` does not evaluate server-side rules and will report success
against a branch that would reject the real push. `gh api repos/OWNER/REPO/rules/branches/main`
lists what actually applies.

Large or load-bearing changes take **more than one review pass**. A change to
the runner, the mutation gate, the case-tree format, or anything a published
release depends on is load-bearing by definition.

Conventional Commits: `type(scope): description`. Imperative, lowercase, no
trailing period, subject ≤ 72 characters. One logical change per commit.
**No AI attribution in commits or PR bodies** — no co-author trailer, no
generated-with footer, no session URL.

---

## 4. Evidence

**Measure before deciding.** Every question this project settled by reading was
wrong at least once; every one settled by measuring was right.

**Never state a number you did not produce.** A figure that reaches a spec, a
README, a commit message or an issue carries the command that produced it. An
estimate is fine when labelled as one and misleading when presented as a
measurement.

**Cell counts lie.** Corpus frequency is inflated by replication and fill-down.
The unit that means anything is a *distinct authored expression*, not a cell.
557 of SpreadsheetBench's 2,667 problems ship six files each; a contributing
problem replicates roughly sixfold. See kindspec/rowspec#28.

**Reproduce before reporting.** Inferring a failure from reading code is a guess,
and a wrong guess sends the fix in the wrong direction.

### When measurement cannot settle it

Some questions are not empirical — *djot or markdown*, *what is a block*. For
those: two independent agents argue opposing sides from the same evidence, and
the adjudication is **written into the repository** with the reasoning and the
reversal cost. `research/design-findings/ADJUDICATION.md` is the precedent.

### Existential spikes are pre-registered

When an experiment decides whether a format should exist at all, the criterion
for "found" is written down and committed **before the experiment runs**. This
project has already concluded "do not build this" once, correctly, and that
verdict is only worth anything if the bar could not move afterwards.

**A negative finding is a deliverable.** rowspec's own README says *"if your
table is a list of facts, you probably do not need this."* Hold every kind to
that standard.

---

## 5. Conventions that travel between kinds

**Fixtures are exact bytes.** A case is a directory of real files plus one
`expect.json`, openable in any tool and diffable — the project's own thesis
applied to itself. Never "tidy" a fixture; whitespace hooks are excluded from
case trees for that reason.

**A runner must never import the case definitions.** That is the test of whether
the fixture tree is sufficient for someone else to implement against.

**The mutation gate**: deliberately break the implementation, and the suite must
notice. A surviving mutant is a failure. So is a **stale** one whose pattern no
longer matches the source — because a check that quietly stopped running is the
failure this project keeps finding in itself.

**New behaviour needs a fixture, and the fixture must be able to fail.**

**Do not add a case in the same change that adds the code it covers.** This is
the one hard process rule and it exists because it was violated three times
during rowspec's design.

**Errors name entities, never offsets.** `#REF!(unit)`, not "error at line 7".

**Do not commit derived values.**

**Correctness may not depend on a merge driver, a clean/smudge filter, or a
hook.** None of them travel. If correctness needs one, it is lost the moment
someone clones without it, or the forge merges server-side.

**One MODEL, several grammars.** Do not reuse one kind's syntax for another.
One syntax is a trap; JATS learned this in 2003 and encoded the lesson
architecturally.

---

## 6. Licensing

Per directory, deliberately.

    SPEC.md, docs/            CC-BY-4.0
    conformance/cases/        CC0-1.0
    conformance/*.py          MIT
    reference/, tests/        Apache-2.0 OR MIT

Fixtures are CC0 with no prose attached so they can be vendored into an
implementation in any language under any licence. Embedding test cases inside a
copyleft specification document is the mistake this split exists to avoid.

Contributions are under a DCO sign-off, not a CLA.

---

## 7. Escalate, do not decide

Stop and ask rather than proceeding, for:

- anything that reverses a decision recorded in a repository's `ROADMAP.md` or
  an adjudication
- deleting data, force-pushing, or rewriting published history
- publishing anything publicly that names a private individual or their private
  infrastructure
- taking a new runtime dependency in a `reference/` tree
- a spike result that would kill a kind

Everything else: decide, document the reasoning where the next agent will find
it, and keep moving.
