# .github

Org-level defaults for [kindspec](https://github.com/kindspec).

- `scripts/check_required_checks.py` — fails when a job that runs on pull
  requests gates no merge, a required check never reports or can be skipped,
  or a required check also comes from a `push` run on the pull request's
  branch, in the same workflow or another; its mutation
  sweep is `scripts/sweep_check_required_checks.py`.
  `.github/workflows/required-checks-audit.yml` runs it daily, and on demand.
- `profile/README.md` — the org landing page.
- `profile/assets/` — the org mark.
- `scripts/generate_logo.py` — regenerates that mark.
- `LICENSE` — per directory: `scripts/` MIT, everything else CC-BY-4.0.

Issue templates are in `.github/ISSUE_TEMPLATE/`, and the pull request template
is `.github/PULL_REQUEST_TEMPLATE.md`. GitHub uses each in every kindspec
repository that has none of its own. The shared CI workflow is not here: it is
kindkit's reusable
[`kind.yml`](https://github.com/kindspec/kindkit/blob/main/.github/workflows/kind.yml).
