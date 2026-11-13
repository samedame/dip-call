"""Confidence tier (added 2026-11-13). NOT a win probability: even the best tier won only 37-59% of trades in the backtest.

Points (0-3), one each: SPY more than 5% below its 52-week high; VIX above 22; two or more of the four distinct signals (IBS<0.20, close<SMA50, IBS<0.10, RSI<35 & DeM<0.30) firing the same day.
The three conditions were chosen by me after the sprint research showed sell-offs mattered, then tested 2001-2013 vs 2014-2026: NOT pre-registered. The tier sorted S1 and K2 out of sample;
it did NOT separate K1 (high +34% vs low +31%) and K3/K4 score 2-3 almost always. The paper ledger tracks results by tier, so this score is forward-tested too."""
import numpy as np

HIGH_MIN = 2
SCORED = {"S1", "K2"}          # rules where the tier held up out of sample

# Backtest by points, mean net return per trade / win rate / n. TE = 2014-2026 (out of sample), ALL = 2001-2026. From conf.py / conf2.py in the sprint folder.
CAL = {
    "S1": {"TE": {0: (-0.19, 0.19, 112), 1: (-0.03, 0.26, 198), 2: (0.72, 0.44, 71), 3: (1.08, 0.37, 94)},
           "ALL": {0: (-0.16, 0.20, 194), 1: (0.03, 0.27, 350), 2: (0.59, 0.34, 167), 3: (1.03, 0.36, 287)}},
    "K2": {"TE": {1: (0.04, 0.45, 161), 2: (0.38, 0.59, 46), 3: (0.33, 0.51, 72)},
           "ALL": {1: (0.08, 0.46, 290), 2: (0.27, 0.50, 94), 3: (0.33, 0.50, 202)}},
}


def drawdown(close):
    """Close / trailing 252-bar high - 1 (min 120 bars), the research definition. Last element is today's."""
    c = np.asarray(close, float)
    out = np.full(len(c), np.nan)
    for i in range(len(c)):
        lo = max(0, i - 251)
        if i - lo + 1 >= 120:
            out[i] = c[i] / c[lo:i + 1].max() - 1
    return out


def drawdown_last(close):
    c = np.asarray(close, float)
    w = c[-252:]
    return float(w[-1] / w.max() - 1) if len(w) >= 120 else float("nan")


def nfire(sigarr, i=-1):
    return int(sum(bool(sigarr[k][i]) for k in ("IBS20", "TRENDDN", "IBS10", "DIP2")))


def points(dd, vix, n_fire):
    """0-3, or None when VIX or drawdown is unavailable."""
    if vix is None or dd is None or not np.isfinite(dd):
        return None
    return int(dd < -0.05) + int(vix > 22) + int(n_fire >= 2)


def tier(rule_id, pts):
    if pts is None:
        return "UNSCORED"
    if rule_id not in SCORED:
        return "N/A"
    return "HIGH" if pts >= HIGH_MIN else "LOW"


def describe(rule_id, pts, dd, vix, n_fire):
    """One alert line. Returns (text, tier)."""
    t = tier(rule_id, pts)
    base = f"  Confidence: {pts}/3 points (SPY {dd * 100:+.1f}% from 52-week high, VIX {vix:.1f}, {n_fire} signal{'s' if n_fire != 1 else ''} firing)" if pts is not None else "  Confidence: unscored (VIX or history unavailable)"
    if pts is None:
        return base, t
    if t == "N/A":
        return base + f"; the score did not separate {rule_id}'s results in the backtest, so no tier is given. Not a win probability.", t
    te, al = CAL[rule_id]["TE"].get(pts), CAL[rule_id]["ALL"].get(pts)
    cal = ""
    if te and al:
        cal = f" Backtest at {pts} point{'s' if pts != 1 else ''}: 2014-2026 mean {te[0] * 100:+.0f}% per trade, {te[1] * 100:.0f}% win (n={te[2]}); 2001-2026 {al[0] * 100:+.0f}%, {al[1] * 100:.0f}% (n={al[2]})."
    return base + f" -> tier {t}.{cal} Not a win probability: the median trade still lost money in every tier. Rule chosen after the research, not pre-registered.", t
