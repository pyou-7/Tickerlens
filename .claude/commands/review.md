# /review — Pre-push code review

Invoke the `code-reviewer` subagent on the current diff and print a severity-grouped report.

## When to use

Run this before every `git push`, or any time you want a read-only second opinion on staged or
recent changes. The pre-commit hook runs this automatically on `git commit`, but `/review` is
useful for a manual check at any point.

## What it does

1. Invokes the `code-reviewer` agent (defined in `.claude/agents/code-reviewer.md`).
2. The agent reads `.claude/agent-memory/code-reviewer/MEMORY.md` for project patterns.
3. Reviews the current diff (`git diff --cached`, or `git diff main` if nothing is staged).
4. Returns a report grouped as **Critical / Warning / Suggestion**.
5. Flags any infra changes (new deps, migrations, new modules, EDGAR pipeline changes) with
   a ready-to-paste entry for `docs/DECISIONS.md`.
6. Ends with a verdict: `VERDICT: SAFE TO PUSH` or `VERDICT: FIX FIRST`.

## Usage

```
/review
```

No arguments. The agent determines the diff scope automatically.

## After the review

- If verdict is **SAFE TO PUSH**: proceed with your push.
- If verdict is **FIX FIRST**: address the Critical findings, then run `/review` again.
- If an infra-change entry was emitted: paste it into `docs/DECISIONS.md` before pushing.

## Override (emergencies only)

To skip the pre-commit hook on a specific commit:
```bash
SKIP_CLAUDE_REVIEW=1 git commit -m "..."
```
or:
```bash
git commit --no-verify -m "..."
```
Both are escape hatches for genuine emergencies. Prefer fixing the issues instead.
