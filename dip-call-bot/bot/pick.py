"""Contract selection: expiry = the session `tenor` sessions after the entry session (SPY lists daily expiries), strike = call whose listed delta is nearest the rule's delta."""
import datetime as dt

FEE = 0.04   # per contract per side, as in the research


def house_half_spread(p):
    return max(0.01, 0.01 * p)


def pick_call(rows, target_exp, target_delta):
    """Nearest listed expiry on or after target_exp; among its calls with a two-sided market, the one with delta closest to target. None if nothing qualifies."""
    exps = sorted({r["exp"] for r in rows if r["exp"] >= target_exp})
    for e in exps[:3]:
        cands = [r for r in rows if r["exp"] == e and r["cp"] == "C" and r["bid"] > 0 and r["ask"] > 0 and r["delta"] > 0]
        if cands:
            best = min(cands, key=lambda r: abs(r["delta"] - target_delta))
            if abs(best["delta"] - target_delta) <= max(0.03, 0.5 * target_delta):
                out = dict(best)
                mid = (best["bid"] + best["ask"]) / 2
                out["spread"] = best["ask"] - best["bid"]
                out["spread_vs_house"] = out["spread"] / (2 * house_half_spread(mid))
                return out
    return None
