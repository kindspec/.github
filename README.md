# .github

Org-level defaults for [kindspec](https://github.com/kindspec).

- `scripts/check_required_checks.py` — fails when a job that runs on pull
  requests gates no merge, or a required check never reports; its mutation
  sweep is `scripts/sweep_check_required_checks.py`.
- `profile/README.md` — the org landing page.
- `profile/assets/` — the org mark.
- `scripts/generate_logo.py` — regenerates that mark.

Shared workflows, issue templates, and the other org-wide defaults GitHub
reads from this repo will land here as they are written.
