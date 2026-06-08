# /phase-complete — Distill and close a phase

Safely close out a phase by promoting durable knowledge into the permanent docs, then archiving
the ephemeral phase file. **Never delete a phase file without distilling it first.**

## When to use

Run this when a phase's goals are met and you're ready to start the next phase.

## Workflow (follow in order — do not skip steps)

### Step 1 — Identify the phase file

Find `docs/progress/PHASE-<n>.md` for the phase being closed.
If it doesn't exist, ask the user which phase to close before continuing.

### Step 2 — Distill durable content

Read the phase file carefully and promote content into the appropriate permanent documents:

**→ `docs/ARCHITECTURE.md`**
Promote any architectural changes: new layers, new data flows, new key files, new design
decisions that changed how the system works. Update existing sections if the phase changed them.

**→ `docs/DECISIONS.md`**
For every decision listed in the phase file's "Decisions Made This Phase" table, add an entry
in `docs/DECISIONS.md` if one doesn't already exist. Format:
```
## YYYY-MM-DD — <short title>

**What:** One sentence on what changed or was decided.
**Why:** The motivation.
**Alternatives considered:** What else was evaluated, or "None recorded."
```

**→ `CLAUDE.md`** (root)
Promote any new project-wide conventions, critical rules, or stack changes that all future
agents must know. Update the "Current implementation snapshot" section with new modules.

**→ `.claude/agents/xbrl-specialist.md`**
If the phase uncovered new SEC/XBRL edge cases, add them to the xbrl-specialist knowledge base.

### Step 3 — Verify distillation is complete

Before archiving, confirm:
- [ ] Every open question in the phase file is either answered (in ARCHITECTURE/DECISIONS) or
      carried forward explicitly to the next phase file.
- [ ] Every decision in the "Decisions Made" table has a `docs/DECISIONS.md` entry.
- [ ] The "Gotchas" section has been reviewed — surprising findings belong in agent memory or
      specialist docs, not just the phase file.

### Step 4 — Archive the phase file

Move (do not delete) the phase file to `docs/progress/_archive/`:
```bash
mkdir -p docs/progress/_archive
mv docs/progress/PHASE-<n>.md docs/progress/_archive/PHASE-<n>.md
```

### Step 5 — Create the next phase file

Copy the template and fill in the goal:
```bash
cp docs/progress/PHASE-template.md docs/progress/PHASE-<n+1>.md
```

Update `docs/PROJECT_STATUS.md` to reflect the new current phase.

---

## What NOT to do

- Do not delete the phase file without running Steps 2–3 first.
- Do not promote git-history content (commit messages, diff summaries) — only capture the WHY
  and the current-state model that isn't already in the code.
- Do not carry forward resolved questions — close them in DECISIONS.md and drop them from the
  next phase file.
