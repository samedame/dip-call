import math
from .pick import FEE

SPRINT_DEFAULT = 0.75     # the research champion's share of equity per trade (median result $174 from $1,500)
KELLY_SCALE = 0.5         # half Kelly
TOTAL_CAP = 0.35          # maximum share of equity across rules that fire the same day


def contracts(equity, fraction, ask):
    """Whole contracts so that cost (ask + fee) stays within fraction of equity."""
    if ask <= 0 or equity <= 0 or fraction <= 0:
        return 0
    return max(0, int(math.floor(fraction * equity / (ask * 100 + FEE))))


def paper_contracts(equity, fraction, ask):
    """Paper ledger sizing is fractional (contract-equivalents), the way the research's Kelly table assumed continuous sizing. Real accounts need whole contracts."""
    if ask <= 0 or equity <= 0 or fraction <= 0:
        return 0.0
    return round(fraction * equity / (ask * 100 + FEE), 3)


def paper_fraction(rule):
    return rule.kelly * KELLY_SCALE


def suggested_fractions(firing, profile, sprint_fraction=SPRINT_DEFAULT, cap=TOTAL_CAP):
    """Shares of real equity to suggest for the rules firing today. profile 'sustainable' = half-Kelly on K rules (scaled to the cap); 'sprint' = champion only."""
    if profile == "sprint":
        return {r.id: sprint_fraction for r in firing if r.id == "S1"}
    f = {r.id: paper_fraction(r) for r in firing if r.family == "kelly"}
    tot = sum(f.values())
    if tot > cap:
        f = {k: v * cap / tot for k, v in f.items()}
    return f
