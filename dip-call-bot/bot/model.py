"""The research's option-price model, ported without scipy: VIX-family term structure -> ATM stdev -> smile (12 Nov 2026 SPY chain) -> Black-Scholes.
Used only to compare the live ask with the price the research assumed (the research's weakest link). Numbers must match engine.py exactly (tested)."""
import json, math, os
from statistics import NormalDist
import numpy as np

RHO9, RHO30 = 0.88, 0.82
_N = NormalDist()
_SMILE = None


def _load():
    global _SMILE
    if _SMILE is None:
        with open(os.path.join(os.path.dirname(__file__), "smile_spy.json")) as f:
            d = json.load(f)
        _SMILE = dict(cals=np.array(d["cals"], float), grid=np.array(d["grid"], float), G=np.array(d["G"], float), asof=d["asof"])
    return _SMILE


def smile_g(m, cal):
    s = _load()
    m = float(np.clip(m, -4.5, 4.5))
    cals = s["cals"]
    i = int(np.clip(np.searchsorted(cals, cal), 1, len(cals) - 1))
    c0, c1 = cals[i - 1], cals[i]
    w = float(np.clip((cal - c0) / (c1 - c0), 0, 1))
    return (1 - w) * np.interp(m, s["grid"], s["G"][i - 1]) + w * np.interp(m, s["grid"], s["G"][i])


def atm_sd(v1, v9, v30, v93, sess):
    """Total stdev to expiry `sess` sessions out. Inputs are index levels in points (e.g. VIX 18.7)."""
    cal = sess * 1.4
    a, b, c, d = (v1 / 100) ** 2, (v9 / 100 * RHO9) ** 2, (v30 / 100 * RHO30) ** 2, (v93 / 100 * RHO30) ** 2
    if cal <= 9:
        tv = a * 1 + (b * 9 - a * 1) * (cal - 1) / 8
    elif cal <= 30:
        tv = b * 9 + (c * 30 - b * 9) * (cal - 9) / 21
    else:
        tv = c * 30 + (d * 93 - c * 30) * (cal - 30) / 63
    return math.sqrt(max(tv, 1e-10) / 365)


def bs_call(F, K, s):
    s = max(s, 1e-9)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    return F * _N.cdf(d1) - K * _N.cdf(d1 - s)


def _forward(S, carry, cal):
    return S * math.exp(carry * cal / 365)


def price_call(S, K, sess, vols, carry):
    """Research price (per share) of a call `sess` sessions out. vols = dict(v1,v9,v30,v93) in index points; carry = IRX/100 - 0.012."""
    sd = atm_sd(vols["v1"], vols["v9"], vols["v30"], vols["v93"], sess)
    cal = sess * 1.4
    F = _forward(S, carry, cal)
    return bs_call(F, K, sd * smile_g(math.log(K / F) / sd, cal))


def strike_for_delta(S, delta, sess, vols, carry):
    """The research's strike rule: K = F*exp(-z*s + s^2/2) iterated three times with the smile, rounded to a dollar."""
    sd = atm_sd(vols["v1"], vols["v9"], vols["v30"], vols["v93"], sess)
    cal = sess * 1.4
    F = _forward(S, carry, cal)
    z = _N.inv_cdf(delta)
    s = sd
    for _ in range(3):
        K = F * math.exp(-z * s + 0.5 * s * s)
        s = sd * smile_g(math.log(K / F) / sd, cal)
    return float(round(K))
