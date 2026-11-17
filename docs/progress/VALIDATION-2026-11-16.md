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

---

## Push 2 — 2026-11-16 ~22:58 CST (batch 267 + passcode gate)
- **When:** 2026-11-16 ~22:58 CST, on the same transient fine-grained PAT the user pasted at ~21:35 CST (reused within the same active work day per the standing rule; used via env var, never stored).
- **Range:** `8d68de3..3951a2c` — **3 commits**: batch 267 ×2 (BKR 2024-12-31 re-sync, CEO-quote class closed) + passcode gate ×1 (3951a2c: `TICKERLENS_PASSCODE` gate — HMAC cookie + Bearer auth, login page, 17 tests).
- **Result:** push succeeded; after `git fetch origin`, `origin/main` = `3951a2c`, **0 commits ahead**.

## Validation of the pushed code
- **Tests:** full suite run from a clean worktree checkout of pushed HEAD (`3951a2c`): **2379 passed, 0 failed** (58 warnings, pre-existing). The worktree needed the repo `.env`, `tickerlens.db`, and the whole `hidden_files/` dir copied in (the 8 batch-236 gate tests read both `hidden_files/blast233_guidance_new.json` AND `hidden_files/blast235_guidance_new.json` — copying only blast233 left 8 failures; copying the full dir fixed them; the earlier log's "blast233 only" note was incomplete). Same test-harness coupling to local data as before, not a defect in the pushed code.
- **Live routes (dev server on :8123, serving pushed code):** 8/8 HTTP 200 — home, `/company/AAPL`, `/company/AAPL/detail`, `/company/AAPL/compare`, `/company/AAPL/vs/MSFT` (first try 000, slow Yahoo fetch; 200 on retry), `/api/search?q=AAPL`, `/company/BKR`, `/company/NVDA`. Server had died after a runtime restart and was restarted first (setsid/nohup, ungated — no passcode env var, so local dev stays open for loop validation).
- **Railway live gate (public URL, after redeploy):** the push auto-deployed, but the first deployment (started 22:58:35 CST) ran with the gate OFF — the `TICKERLENS_PASSCODE` variable was still staged as an unapplied change when that deployment's container started (race between the variable save ~22:57 and the push). A manual "Deploy Changes" redeploy (started 23:04:12 CST, "Deployment successful" / ACTIVE, same commit 3951a2c) fixed it. Verified live after the redeploy: unauth home 307 → /login; /login 200 with the passcode form; wrong passcode 401; correct passcode 303 + `tickerlens_auth` cookie; home + /company/AAPL 200 with the cookie; `Authorization: Bearer <passcode>` 200. (Two correct-passcode POSTs timed out at 30s immediately after the redeploy — container warm-up; the same POST returned 303 in 0.58s on retry. Transient, not a code defect.) The live site now requires the passcode.
- **Note:** at push time the working tree held the usual untracked batch probe/repair scripts and a modified-but-uncommitted `tickerlens.db` (batch-267 data) — pre-existing pattern, not committed, not pushed.

## Auth
- The pasted PAT was used transiently via env var for this push and the validation-log push below, then forgotten. It was never written to disk, committed, or stored.
- Hands-off pushes still await the user adding the `pyou-7-tickerlens-push` SSH public key to GitHub.
