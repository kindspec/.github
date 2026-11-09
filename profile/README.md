# kindspec

File formats for tables, documents and diagrams that stay correct when several
people edit them in git.

## The problem

Two people add a row to a spreadsheet saved as CSV. `git merge` reports no
conflict, and the total comes out 480 when the truth is 660. A formula pointed
at a position, the rows moved, and nothing warned anyone.

## How it works

Every format follows three rules:

- **Names, not positions.** A formula says `qty * unit`, never `B2 * C2`.
- **Correct or refused.** A file that can't be read correctly is rejected, with
  the reason.
- **Plain git is enough.** No merge driver, no plugin.

Each format is a written spec plus a test suite. The suite merges real branches
with real git, computes the result and checks the numbers. Then it breaks the
implementation on purpose, to prove the tests can fail.

## Try it

Save this as `parts.mdtbl`:

```text
| id     | item   | qty | unit  | total = qty * unit |
| ------ | ------ | --: | ----: | -----------------: |
| r_0001 | widget |  10 | 12.00 |                    |

key   := id
grand := sum(total)
```

Then:

```sh
pip install rowspec
rowspec check .    # will it survive merging?
rowspec eval .     # what do the totals come to?
```

## Repositories

| | what it is | status |
|---|---|---|
| **[rowspec](https://github.com/kindspec/rowspec)** | tables | released, [on PyPI](https://pypi.org/project/rowspec/) |
| **[blockspec](https://github.com/kindspec/blockspec)** | documents | spec, test suite and reference |
| **[nodespec](https://github.com/kindspec/nodespec)** | diagrams | draft spec and checker |
| [kindkit](https://github.com/kindspec/kindkit) | the shared test runner | [on PyPI](https://pypi.org/project/kindkit/) |
| [research](https://github.com/kindspec/research) | the measurements the specs cite | a record |

## Contributing

Issues and pull requests are welcome; see rowspec's
[CONTRIBUTING](https://github.com/kindspec/rowspec/blob/main/CONTRIBUTING.md).
Commits need a DCO sign-off. Specs are CC-BY-4.0, test fixtures CC0, code MIT or
Apache-2.0.
