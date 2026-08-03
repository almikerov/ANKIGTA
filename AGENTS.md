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

Implementation agents verify programmatically — never by driving a GUI with screenshots or synthetic input. Automated evidence comes from disposable copies. Deploying a build and the development tooling into the owner's own server is standing permission and is not verification. See `docs/agents/mta-gta-reference-policy.md`.

### Asking the running server

`tools/devserver/` turns the owner's running server into something an agent can question and drive, rather than asking the owner to press a key and describe what they saw. It produces diagnosis, not evidence: a finding there becomes a test, or it did not happen.
