# Post-push validation — 2026-11-16

## Push
- **When:** 2026-11-16 ~21:36 CST, on the user's pasted transient fine-grained PAT (used via env var, never stored).
- **Range:** `3aa16f8..8d68de3` — **178 commits** (batches 181–266 since the 2026-11-02 push), ending at batch 266 (BNY ×8 re-sync, CEO-quote design question settled).
- **Result:** push succeeded; after `git fetch origin`, `origin/main` = `8d68de3`, **0 commits ahead**.

## Validation of the pushed code
- **Tests:** full suite run from a clean worktree checkout of pushed HEAD (`8d68de3`): **2359 passed, 0 failed** (58 warnings, pre-existing). Two pieces of local state had to be copied into the worktree first, because the suite reads them from the repo root and they are gitignored, not pushed code: the repo `.env` (settings) and `tickerlens.db` (seeded data — 9 tests failed without it), plus `hidden_files/` blast artifacts (8 batch-236 tests read `hidden_files/blast233_guidance_new.json`). With those in place the worktree run matches the working-tree run exactly (2359 green). This is a test-harness coupling to local data, not a defect in the pushed code — noted for a future batch to fix (tests should not depend on untracked local files).
- **Live routes (dev server on :8123, serving batch-266 code):** 8/8 HTTP 200 — home, `/company/AAPL`, `/company/BNY`, `/company/BNY/detail?quarter=Q3%20FY2025`, `/company/CINF`, `/company/DIS`, `/company/V`, `/api/search?q=TT`. Server had to be restarted first (detached server was down after a runtime restart; restarted via setsid/nohup, PID 2829).
- **Note:** at push time the working tree held the usual untracked batch probe/repair scripts (`scripts/batch*_*.py`, `hidden_files/`) — pre-existing pattern, not committed, not pushed.

## Auth
- The pasted PAT was used transiently via env var for this push and the validation-log push below, then forgotten. It was never written to disk, committed, or stored.
- Hands-off pushes still await the user adding the `pyou-7-tickerlens-push` SSH public key to GitHub.
