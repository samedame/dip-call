"""The five rules from the sprint research (SPY only). Every rule is: signal at the close -> buy a far-OTM call with `tenor` sessions to
expiry and about `delta` -> sell at the close `hold` sessions later. Numbers below are copied from the research's kelly.pkl (SPY, house costs;
Kelly fraction fitted on 2001-2013, growth measured on 2014-2026). They are the benchmark the paper ledger is scored against."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    sig: str
    delta: float
    tenor: int
    hold: int
    kelly: float          # fitted full-Kelly share of equity per trade
    per_year: float       # non-overlapping trades a year, 2014-2026
    mean_te: float        # mean net return per trade of premium, 2014-2026
    win_te: float         # share of trades that made money, 2014-2026
    growth_te: float      # log growth a year at the fitted Kelly share, 2014-2026
    family: str           # "kelly" (sustainable) or "sprint" (lottery)


RULES = [
    Rule("S1", "Sprint champion: weak close (IBS<0.20), 0.07-delta call, 5 sessions out, hold 2", "IBS20", 0.07, 5, 2, 0.10, 36.99, 0.265, 0.291, 0.174, "sprint"),
    Rule("K1", "Close below 50-day average, 0.15-delta call, 5 sessions out, hold 2", "TRENDDN", 0.15, 5, 2, 0.10, 38.78, 0.323, 0.355, 0.682, "kelly"),
    Rule("K2", "IBS<0.10, 0.30-delta call, 10 sessions out, hold 2", "IBS10", 0.30, 10, 2, 0.31, 21.73, 0.172, 0.491, 0.527, "kelly"),
    Rule("K3", "RSI<35 and DeMarker<0.30, 0.15-delta call, 2 sessions out, hold 1", "DIP2", 0.15, 2, 1, 0.18, 9.27, 0.635, 0.395, 0.497, "kelly"),
    Rule("K4", "RSI<35 and DeMarker<0.30, 0.30-delta call, 2 sessions out, hold 1", "DIP2", 0.30, 2, 1, 0.21, 9.27, 0.460, 0.462, 0.480, "kelly"),
]
BY_ID = {r.id: r for r in RULES}


def signal_arrays(ind):
    """Boolean arrays (NaN comparisons are False, as in the research) for each signal name."""
    ibs, rsi, dem, sma50, c = ind["ibs"], ind["rsi"], ind["dem"], ind["sma50"], ind["close"]
    with np.errstate(invalid="ignore"):
        return {"IBS20": ibs < 0.20, "IBS10": ibs < 0.10, "TRENDDN": c < sma50, "DIP2": (rsi < 35) & (dem < 0.30)}


def rule_signals(ind):
    s = signal_arrays(ind)
    return {r.id: s[r.sig] for r in RULES}


def schedule(sig, hold):
    """Non-overlapping entries exactly as the research's Kelly table: after an entry at i, the next may be at i+hold."""
    keep = np.zeros(len(sig), bool)
    nxt = 0
    for i in np.where(sig)[0]:
        if i >= nxt:
            keep[i] = True
            nxt = i + hold
    return keep
