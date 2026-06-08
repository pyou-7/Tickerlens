# /status — Session start briefing

Gives a concise orientation at the start of a working session: current phase, what's done,
what's next, and any open blockers.

## What it does

1. Reads `docs/PROJECT_STATUS.md` for current phase and task list.
2. Reads the active phase progress file (`docs/progress/PHASE-<n>.md`) if one exists.
3. Reads `docs/ARCHITECTURE.md` for current system model.
4. Runs `git log --oneline -10` to show recent commits.
5. Checks for any uncommitted changes (`git status --short`).
6. Reports back in a structured, scannable format.

## Output format

```
## Tickerlens — Session Status

**Phase:** <n> — <title>
**Phase goal:** <one line>

### Completed this phase
- <bullet list from PROJECT_STATUS / phase file>

### Up next
- <bullet list of concrete next tasks>

### Open questions / blockers
- <from phase file or PROJECT_STATUS open decisions>

### Recent commits (last 10)
<git log output>

### Working tree
<clean / uncommitted changes>
```

## Usage

```
/status
```

Run at the start of any session to orient yourself (or a new agent) before diving in.
If a phase progress file exists at `docs/progress/PHASE-<n>.md`, the output will be richer —
in-flight work and gotchas are captured there.
