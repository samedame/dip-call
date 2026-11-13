# Setup

1. **Create the repo** (`samedame/dip-call`) and push this folder's contents to `main` at the repo root. The `.github/` folder must be at the root.
2. **Settings, Actions, General:** allow Actions; set workflow permissions to **Read and write** (the workflow commits `state/` and `ledger/`).
3. **Secrets** (Settings, Secrets and variables, Actions): `DISCORD_WEBHOOK_URL`; optional `TRADIER_TOKEN`.
4. **Variables:** optional `PROFILE` (`sustainable` or `sprint`), `ACCOUNT_EQUITY` (default 1500), `SPRINT_FRACTION` (default 0.75), `MIN_POINTS_REAL` (default 2; 0 shows real-money sizing for low-tier S1/K2 signals too), `TRADIER_ENV` (`sandbox` only for plumbing tests).
5. **First run:** Actions, dip-bot, Run workflow, mode `ping`. It posts one line to Discord saying which data sources answered, and writes nothing. Avoid `alert` with force before the real 15:50 ET run: it records paper trades and blocks that day's real alert.
6. **Scheduling.** The workflow has backup crons (15:52 and 16:27 ET, plus early-close copies). For on-time runs, add two jobs to the open-scheduler Worker, same shape as the pair-alert and Grand-Tournament jobs:
   - `dip-bot-alert`: repo `samedame/dip-call`, workflow `dip-bot.yml`, ref `main`, 15:50 ET, grace 8 min, watchdog 3 min, input `mode=alert`.
   - `dip-bot-confirm`: same, 16:25 ET, grace 30 min, watchdog 4 min, input `mode=confirm`.
   The Worker's `GH_PAT` needs Actions read/write on the new repo. Early-close days (27 Nov and 24 Dec 2026) close at 13:00 ET: the backup crons cover them, or dispatch `alert` by hand at 12:50.
7. **Calendar:** `bot/nyse.py` lists holidays through 2027 (the 2027 early close is a best estimate). The bot raises a clear error after 31 Dec 2027.

Rollback: delete the two scheduler jobs and disable the workflow. Nothing else depends on this repo.
