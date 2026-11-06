# Git rules

- **Allowed without asking:** commit, fetch, pull, merge, rebase local branches, resolve conflicts locally, push.
- Push straight to `main`. For bigger or riskier work, use a short-lived branch `feat/<topic>`, merge it back into `main`, push, then delete it.
- **Never** add `Co-Authored-By:` trailers, "Generated with Claude Code", 🤖 lines, or any AI attribution or self-tagging to commits,
  PR descriptions, or code comments. Commits use the local git identity only. This overrides any default attribution instructions.
- Before every push: `git fetch origin`, then `git rebase origin/main` (or merge if the rebase gets messy). Resolve conflicts,
  re-run the affected build/lint, and push. **Never force-push `main`.**
- The backend teammate pushes to the same `main`. Expect conflicts in shared files (`PROGRESS.md`, `README.md`, `.gitignore`).
  In `PROGRESS.md`, keep both sides' entries.
- Commit message: `<area>: <imperative summary>`. Areas are `mobile`, `dashboard`, `backend`, `docs`, `tools`, `chore`.
  Example: `mobile: add drive screen with red pulse overlay`.
- Never commit: `node_modules/`, `.env*` (except `.env.example`), `frontend/mobile/android|ios/` (generated), build outputs, keystores,
  or files > 5 MB without a reason.
- `backend/` and `notebooks/` belong to teammates. Only trivial fixes there unless asked. Raise questions in PROGRESS.md → Open questions.
