# Research provenance

Source: `claude/1500-to-100k-sprint-verdict-2026-11-13` (project doc) and `sprint_to_100k_research.zip` (code, result tables, data).

## What was tested
64,876 fixed policies and one adaptive policy from $1,500 over about 6,245 overlapping 33-session windows (2001-2026), Black-Scholes prices with a smile from the live 12 Nov 2026 Cboe chain and an at-the-money level from the VIX family; costs: half-spread max(1 cent, 1% of premium) plus $0.04 per contract per side. Result: **no strategy reaches $100,000 reliably** (best 1.94% of windows; 0 of 1,385 windows from a market like today's). The dip-rebound call family was the only one that held in both halves of history.

## How the rules were chosen
Kelly fractions were fitted on 2001-2013 and growth measured on 2014-2026 over 7,420 signal-and-structure combinations; K1 to K4 are the table's top rows by the smaller of the two halves' growth, S1 is the sprint-simulation champion. This is **not pre-registered**, so the out-of-sample growth is an upper-leaning estimate.

## What the bot reproduces exactly (tests)
- Indicators and all five signals match the research's code on all 8,296 daily rows (max indicator difference below 1e-9). A 5-year window, as fetched live, gives the same latest signals.
- Non-overlapping trade counts per year match the Kelly table within 6%.
- The ported price model (term structure, smile, Black-Scholes) and strike rule match the research engine to 1e-9 on 300 sampled rows.

## What the bot adds (not in the research)
- Real chain quotes: the asks of the five picked contracts on the 12 Nov 2026 close were 0.98x (K2), 1.07x (K3), 1.10x (K4), 1.12x (K1) and 1.13x (S1) the research model's price. A live dry run on 13 Nov showed 1.02x to 1.05x. One snapshot each; the paper ledger is how this gets measured properly.

## Confidence tier (added after the research)
Tested on the research's own trades: terciles and a ridge-regression score fitted on 2001-2013, applied to 2014-2026, plus the simple 0-3 point count the bot uses. The point count was no worse than the fitted score. High vs low tier: S1 +93% vs -9% mean per trade (2014-2026, 165 vs 310 trades), K2 +35% vs +4%, K1 +34% vs +31% (no separation). By year, high beat low in 8 of 12 years for S1 and 5 of 9 for K2. Not pre-registered; the conditions were picked knowing sell-offs matter. Code: `conf.py`, `conf2.py` in the sprint folder; calibration numbers are copied into `bot/score.py`, and the bot's points reproduce the research's on all 7,996 days checked (`tests/test_score.py`).

## Known gaps
- Cboe quotes are ~15 minutes delayed; without Tradier the 15:50 alert prices off a 15:35 chain.
- The alert uses a provisional daily bar; the final close can change a signal (the confirm step voids those paper entries). If you trade on the alert you carry that risk.
- Entry and exit are quoted at 15:50 ET, not at the close fill the research assumed.
- Whole-contract sizing is not modelled in the research; see README.
- One underlying (SPY). The research's QQQ results were not carried over.
- Verified offline against fixtures and a live dry run of the alert on 13 Nov 2026. Not verified: a real GitHub Actions run, a real Discord post, Tradier with a real token (tested against a mock of its documented response), a confirm run on a real close.
