# kindspec

**A specification and conformance suite per artifact kind.**

Knowledge artifacts — tables, documents, canvases — are edited by several
people over years, and version control is where that happens. These formats are
specified so that a repository full of them stays *correct*, and each
specification ships with an executable conformance suite that measures whether
an implementation actually conforms.

## The problem, stated once

Two branches insert a row into a spreadsheet exported as CSV. Stock `git merge`
merges them cleanly, with no conflict and no marker anywhere, and the total is
480 where the truth is 660. LibreOffice confirms it. A structural merge tool
gets the *rows* perfectly right and produces the identical wrong answer, because
no merge algorithm can see that the string in a cell encodes a position.

That is not a merge bug. It is a **representation** bug, and it is only fixable
in the representation:

- **Addressed by name, never by position.** `A1` is a coordinate; a column name
  is not.
- **Correct or refused, never quietly wrong.** A file that cannot be understood
  is rejected, loudly, rather than degraded into a different file that happens
  to parse.
- **Right under stock git, with none of this installed.** If correctness needs
  a merge driver, then correctness is lost the moment someone clones without
  one, or the forge merges server-side.

## The kinds

Each is named after its unit of identity, because identity is the hard part of
every one of them.

| | unit | identity | status |
|---|---|---|---|
| **rowspec** | rows | opaque row ids | draft 0, implemented |
| **blockspec** | blocks | deliberately no minted ids | **not started** |
| **nodespec** | nodes | named, not positional | **not started** |

Only rowspec exists. The other two are a named intention and a settled
identity decision, not a draft — there is no specification for either, and
saying so is cheaper than being asked.

## The suite is the deliverable

The specification exists so the conformance suite has something to check. The
suite checks out two branches, runs stock `git merge`, **evaluates the merged
file, and asserts on the computed number** — because a merge that produces a
well-formed file with a wrong total is exactly the failure that has no marker,
and nothing else measures it.

Behind that sits a mutation gate: the implementation is deliberately broken in
dozens of specific ways, and the suite must notice every one. A mutant that
survives is a hole in the suite and is reported as a failure, not a warning.

## Two standing rules

**The conformance suite is not written by whoever writes the implementation.**
This is a role, not a review step. It has been tested the hard way: three
separate times, an enumerator checking their own work reported full coverage,
and an adversary then found silently-wrong cases in the same code. On the most
recent pass the two halves were commissioned in parallel and could not see each
other — the independent author's cases killed 7 of 8 mutants written blind, and
found a live defect that returned a plausible number in every row.

**A check that cannot fail must never report a pass.** This project has now
reproduced that failure ten times in its own tooling: a runner that walked an
empty directory and printed `0 failures` over 226 unopened cases, a mutation
gate that disarmed itself on a reformat, a canonicaliser that scored 129/131
while being the identity function, a differential harness whose injected defect
silently stopped applying. Every one was caught by a mechanical check rather
than by review. It is the most transferable thing here and it has nothing to do
with tables.

## Licensing

Per directory, deliberately. Specifications are CC-BY-4.0; conformance fixtures
are CC0-1.0 so they can be vendored into an implementation in any language under
any licence; runners are MIT; reference implementations are Apache-2.0 OR MIT.
Contributions are under a DCO sign-off, not a CLA.

Embedding test cases inside a copyleft specification document is the mistake
this split exists to avoid.
