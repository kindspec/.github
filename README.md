# .github

Org-level defaults for [kindspec](https://github.com/kindspec).

- `scripts/check_required_checks.py` — fails when a job that runs on pull
  requests gates no merge, or a required check never reports; its mutation
  sweep is `scripts/sweep_check_required_checks.py`.
- `profile/README.md` — the org landing page.
- `profile/assets/` — the org mark.
- `scripts/generate_logo.py` — regenerates that mark.
- `LICENSE` — per directory: `scripts/` MIT, everything else CC-BY-4.0.

Issue templates are in `.github/ISSUE_TEMPLATE/`. GitHub uses them in every
kindspec repository that has no `.github/ISSUE_TEMPLATE/` of its own. Shared
workflows and the other org-wide defaults will land here as they are written.
