# dip-call-bot

Alert-only bot built from the **$1,500 to $100,000 sprint research** (2026-11-13). It watches SPY at the close for the dip-rebound signals that won the research, picks the matching far-out-of-the-money call from the live option chain, tells you what it would cost and when to sell, and keeps a **paper ledger of real quotes** so the research's modelled option prices can be tested against the market. It never places an order.

**Label on every alert: RESEARCH SIGNAL, NOT ADVICE.** The research found no strategy that turns $1,500 into $100,000 reliably (best 1.94% of historical windows, about zero from a market like today's). This bot does not change that. Its honest job is to forward-test the one edge that survived: buying SPY calls after weak closes.

## What it does each day

| Time (ET) | Mode | What happens |
|---|---|---|
| about 15:50 | `alert` | Reads SPY's daily bar so far (Yahoo), computes the five rules' signals on that provisional bar, closes paper positions that are due (at the bid), and for each rule that fires picks the contract from the Cboe chain, records a **provisional** paper entry at the ask, and posts to Discord. |
| after the close | `confirm` | Re-reads the final bar. A provisional entry whose signal still holds is confirmed; one that does not is **voided** and never counted. Logs the day's signals and posts the forward-test scorecard. |

## The five rules (SPY only, from the research's Kelly table)

Each rule: signal at the close, buy a call with the listed delta and sessions to expiry, sell at the close `hold` sessions later, one position per rule at a time. Backtest columns are 2014-2026 with the research's modelled prices and house costs.

| ID | Signal at the close | Call | Hold | Trades/yr | Mean per trade | Winners | Kelly share |
|---|---|---|---|---|---|---|---|
| S1 | IBS < 0.20 (weak close) | 0.07 delta, 5 sessions out | 2 | 37 | +27% | 29% | 10% |
| K1 | Close below 50-day average | 0.15 delta, 5 out | 2 | 39 | +32% | 36% | 10% |
| K2 | IBS < 0.10 | 0.30 delta, 10 out | 2 | 22 | +17% | 49% | 31% |
| K3 | RSI(14) < 35 and DeMarker(14) < 0.30 | 0.15 delta, 2 out | 1 | 9 | +64% | 40% | 18% |
| K4 | same as K3 | 0.30 delta, 2 out | 1 | 9 | +46% | 46% | 21% |

S1 is the research's sprint champion (75% of equity per trade reached $100k in 1.7% of windows; median result $174). K1 to K4 are the Kelly-sized "sustainable" rules.

## Confidence tier (v1.1)

Every alert shows a 0 to 3 point score, one point each for: SPY more than 5% below its 52-week high; VIX above 22; two or more of the four distinct signals firing the same day. **It is a filter, not a win probability.**

- **S1 and K2 get a tier** (HIGH at 2 to 3 points, LOW at 0 to 1) because the score sorted their trades out of sample (2014-2026 mean per trade / win rate): S1 0 pts -19% / 19%, 1 pt -3% / 26%, 2 pts +72% / 44%, 3 pts +108% / 37%; K2 1 pt +4% / 45%, 2 pts +38% / 59%, 3 pts +33% / 51%.
- **K1, K3 and K4 show the points but no tier**: K1's high and low groups performed the same (+34% vs +31%) and K3/K4 almost always score 2 to 3.
- **Real-money lines:** for S1 and K2 below `MIN_POINTS_REAL` points (default 2) the alert says NOT suggested. The paper ledger still records every signal with its points and tier, so the score is forward-tested too (`ledger/trades.csv` columns `points`, `tier`; the daily confirm post prints results by tier next to the backtest).
- **Limits:** the three conditions were chosen after the sprint research showed sell-offs mattered (not pre-registered); high-tier trades cluster in sell-offs (2022 is 43 of S1's 165); the median trade lost money in every tier (S1 high: median -54%, 40% win); at a 15% higher entry volatility than modelled S1's high-tier mean falls from +93% to +11%.

## Profiles (what the alert suggests for real money)

- `sustainable` (default): half the fitted Kelly share per K rule, scaled so the rules firing the same day total at most 35% of `ACCOUNT_EQUITY`.
- `sprint`: S1 only, at `SPRINT_FRACTION` (default 0.75, the research champion). Every alert then carries the warning that the median outcome at that size is $174 left from $1,500.

The paper ledger always uses half-Kelly fractional sizing for all five rules regardless of profile, so the scorecard is comparable across rules.

## What this can and cannot show

- **Within weeks:** whether real asks and bids match the research's modelled prices (`ask/model` ratio and spread vs the research's house spread are logged on every entry). On the 12 Nov 2026 close, the five picked contracts' asks were 0.98x to 1.13x the model.
- **Not for years:** whether the *edge* is real. Per-trade returns are very noisy (S1: mean +27%, standard deviation 276%, 29% winners). About 430 S1 trades are needed for the mean to be two standard errors from zero (about 12 years at 37 a year); K1 about 146, K2 101, K3 59, K4 49. Treat the ledger as a pricing and execution test, not proof of profit.
- **Whole contracts:** the research's Kelly table assumed continuous sizing. At $1,500, half-Kelly is $75 to $230 per trade, which buys zero whole contracts of K1, K2 or K4 (a K1 call costs about $110). The alert says so rather than rounding up. Only S1's cheap 0.07-delta call fits a small account.

## Data sources

- SPY daily bars and the VIX family: Yahoo Finance chart API (no key).
- Option chain: Cboe delayed quotes (free, **about 15 minutes late**, so a 15:50 alert prices off a 15:35 chain). Set `TRADIER_TOKEN` for a live bid/ask on the picked contract (read-only quote endpoint; same secret name as Grand-Tournament).

## Run it

```
pip install -r requirements.txt
python -m bot.run alert --force --dry     # live data, prints, writes nothing
python -m bot.run status
python -m pytest -q                        # 29 tests, offline
```

Environment: `DISCORD_WEBHOOK_URL`, `TRADIER_TOKEN`, `TRADIER_ENV` (`sandbox` for delayed test data), `PROFILE`, `ACCOUNT_EQUITY`, `SPRINT_FRACTION`, `MIN_POINTS_REAL`. Setup on GitHub Actions and the Cloudflare scheduler: `docs/SETUP.md`. Provenance and limits: `docs/RESEARCH.md`.
