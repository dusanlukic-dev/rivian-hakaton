# Shared-knowledge protocol (PROGRESS.md + knowledge books)

Several agents and teammates work in parallel. These files are how nobody gets lost:

1. **Start of a task:** read `PROGRESS.md`, then the knowledge book for your area (`.claude/knowledge/*.md`, index in `.claude/CLAUDE.md`).
2. **End of a task (before the final commit):** update `PROGRESS.md`:
   - move items between *Next* / *In progress* / *Done*
   - add bugs to *Known issues* with repro steps and the suspected cause, and remove fixed ones
   - add one line to the *Session log* (date, who/agent, what changed)
   - keep it short and link to files instead of pasting code
3. **Non-obvious facts** (gotchas, version quirks, device behaviour, verified/unverified assumptions) go into the matching knowledge
   book, not only into PROGRESS.md.
4. **Decisions with alternatives**: append to `.claude/knowledge/decisions.md`.
5. **A workflow you did twice, or one that was tricky**: turn it into a skill at `.claude/skills/<name>/SKILL.md` and list it in `.claude/CLAUDE.md`.
6. **A contract change** (WebSocket messages): update `.claude/knowledge/ws-protocol.md` and both clients' adapters in the same commit.
