## Agent skills

### Issue tracker

Specs and issues are tracked as local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default triage label vocabulary is used. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses single-context domain documentation. See `docs/agents/domain.md`.

### Testing the Lua resource

Server-side Lua is tested by running it in a real Lua 5.1 interpreter, not by
searching its source text. See `docs/agents/lua-testing.md`.

### MTA/GTA environment boundary

Implementation agents verify programmatically — never by driving a GUI with screenshots or synthetic input — and never modify the installed MTA:SA or GTA:SA tree. Launching disposable copies is allowed. See `docs/agents/mta-gta-reference-policy.md`.
