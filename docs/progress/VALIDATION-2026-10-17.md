# Post-push validation — 2026-10-17 (evening CDT)

Push: 85 commits (`2ab0d84..e3d7b22`, batches 47–85) pushed to origin/main
via user-supplied transient PAT (used once via env var, never stored).
Queue after push: 0 ahead of origin/main. Verified with
`git fetch origin && git status -sb && git rev-list --count origin/main..main`.

## Test suite
- `.venv/bin/python -m pytest tests/ -q`: **735 passed**, 0 failed (37s).
- `git diff --check`: clean.

## Live routes (dev server :8123, restarted on pushed code)
| Route | Status |
|---|---|
| `/` | 200 |
| `/company/NVDA` | 200 |
| `/company/OXY` | 200 |
| `/company/ABT` | 200 |
| `/company/ABT/tearsheet` | 200 |
| `/company/NVDA/compare` | 200 |
| `/company/OXY/detail` | 200 |
| `/calendar` | 200 |
| `/company/DDOG` | 200 |

9/9 green. (Two initial 404s during validation were wrong paths in the
check itself — `/tearsheet/NFLX`, `/compare` — not app failures; correct
paths `/company/{ticker}/tearsheet` and `/company/{ticker}/compare`
return 200.)

## Notes
- First push attempt with `x-access-token:` URL format failed with an auth
  error; retry with `pyou-7:<token>@` format succeeded. Token is transient
  and was not stored.
- DB state at push: 233 companies seeded.
