---
name: ship
description: Finish a unit of work in this repo. Update PROGRESS.md and any knowledge books, commit with the house message style (never any AI attribution or Co-Authored-By trailer), sync with origin/main (fetch + rebase, resolve conflicts), verify, and push to main. Use at the end of every task, or when the user says commit, push, ship, sync or save progress.
---

# Ship workflow

The user pre-authorized commit, push, merge and conflict resolution without asking (`.claude/rules/git.md`).

1. **Verify** what you touched:
   - mobile: `npm run lint && npm run typecheck` in `frontend/mobile`
   - dashboard: `npm run build && npm run lint` in `frontend/dashboard`
   - If verification fails, fix it, or note it under *Known issues* in PROGRESS.md and say so in the commit body.
2. **Update shared knowledge** (`.claude/rules/progress.md`): PROGRESS.md (status, bugs, a session-log line), any knowledge-book
   facts you learned, and decisions.md if you decided something.
3. **Review the diff:** `git status` and `git diff --stat`. Make sure there are no secrets, no `.env`, no `android/`, and no large binaries.
4. **Commit:** `git add -A && git commit -m "<area>: <imperative summary>"`, with areas `mobile|dashboard|backend|docs|tools|chore`.
   **No `Co-Authored-By`, no "Generated with", no emoji signature.** Split unrelated changes into separate commits.
5. **Sync:** `git fetch origin && git rebase origin/main`.
   - On conflict: open each file and merge both sides' intent. For `PROGRESS.md`, keep both entries. For lockfiles, take
     theirs and re-run `npm install` in that app. Then `git add <file> && git rebase --continue`.
   - If the rebase gets hairy: `git rebase --abort && git merge origin/main`.
   - Re-run step 1 if the incoming changes touch your area.
6. **Push:** `git push origin HEAD:main` (from a feature branch: merge it into main first, push, then `git branch -d feat/x`). Never force-push main.
7. Report the commit hash(es) and anything left undone.
