# Post-push validation — 2026-11-22

## Push
- **When:** 2026-11-22 ~22:34 CST, on the user's pasted transient fine-grained PAT (used via env var, never stored).
- **Range:** `40da65c..f54befe` — **72 commits** (batches 268–303 since the 2026-11-16 push), ending at batch 303 (extension-concept CapEx recovery, LYFT/D/VZ FCF repair).
- **Result:** push succeeded; after `git fetch origin`, `origin/main` = `f54befe`, **0 commits ahead**.

## Validation of the pushed code
- **Tests:** full suite run from a clean worktree checkout of pushed HEAD (`f54befe`): **2640 passed, 0 failed** (58 warnings, pre-existing). The worktree needed the repo `.env`, `tickerlens.db`, and the repo's untracked `hidden_files/` dir copied in (the 8 batch-236 gate tests read `hidden_files/blast233_guidance_new.json` and `blast235_guidance_new.json` relative to the repo root; the first worktree run without them showed exactly those 8 failures, the run with them matched the working-tree run exactly). Same known test-harness coupling to local data as before, not a defect in the pushed code. Note: an initial attempt to copy the goals `hidden_files/` (2.1G, mostly DB backups) into a `/tmp` worktree filled the 512MB tmpfs; the worktree was redone under `~/workspace/` with only the repo's own 39M `hidden_files/` copied.
- **Live routes (dev server on :8123, serving pushed code):** 8/8 HTTP 200 — home, `/company/AAPL`, `/company/LYFT/detail`, `/company/VZ/detail`, `/company/DKNG/detail`, `/api/search?q=AAPL`, `/company/NVDA`, `/company/MDT`. Server had died after a runtime restart and was restarted first (setsid/nohup, ungated).
- **Railway live site (public URL):** unauth home 307 → `/login?next=%2F`; `/login` 200 — the passcode gate is still locked. The push auto-deploys code; the live database still does not refresh on push (entrypoint seeds `/data/tickerlens.db` only on first boot, and this push did not include a DB snapshot commit — the batches 268–303 data fixes live in the uncommitted local `tickerlens.db`), so live data remains Nov 16 vintage until the DB-refresh wiring or a DB snapshot push is approved.
- **Note:** at push time the working tree held the usual untracked batch probe/repair scripts and a modified-but-uncommitted `tickerlens.db` (batches 268–303 data) — pre-existing pattern, not committed, not pushed.

## Auth
- The pasted PAT was used transiently via env var for this push and the validation-log push below, then forgotten. It was never written to disk, committed, or stored.
- SSH pushes remain unavailable from this VM: `ssh -T git@github.com` with the `tickerlens_github` key is reset by the network proxy (198.19.0.1:3128), so the HTTPS PAT route is the only push path from here.
