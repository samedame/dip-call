"""Indicators exactly as in the research (core.py): Wilder RSI(14) seeded at bar 14, DeMarker(14) from simple means, IBS, SMA."""
import numpy as np


def wilder_rsi(c, n=14):
    c = np.asarray(c, float)
    d = np.diff(c, prepend=c[0])
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = np.zeros_like(c), np.zeros_like(c)
    if len(c) <= n:
        return np.full(len(c), np.nan)
    au[n], ad[n] = up[1:n + 1].mean(), dn[1:n + 1].mean()
    for i in range(n + 1, len(c)):
        au[i] = (au[i - 1] * (n - 1) + up[i]) / n
        ad[i] = (ad[i - 1] * (n - 1) + dn[i]) / n
    rsi = 100 - 100 / (1 + au / np.maximum(ad, 1e-12))
    rsi[:n] = np.nan
    return rsi


def _roll_mean(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def demarker(h, l, n=14):
    h, l = np.asarray(h, float), np.asarray(l, float)
    dmax = np.clip(np.diff(h, prepend=h[0]), 0, None)
    dmin = np.clip(-np.diff(l, prepend=l[0]), 0, None)
    a, b = _roll_mean(dmax, n), _roll_mean(dmin, n)
    return a / np.maximum(a + b, 1e-12)


def ibs(h, l, c):
    h, l, c = (np.asarray(x, float) for x in (h, l, c))
    return (c - l) / np.maximum(h - l, 1e-9)


def sma(c, n):
    return _roll_mean(np.asarray(c, float), n)


def compute(bars):
    """bars: dict of equal-length arrays/lists with keys date,o,h,l,c. Returns dict of indicator arrays."""
    h, l, c = (np.asarray(bars[k], float) for k in ("h", "l", "c"))
    return {"close": c, "ibs": ibs(h, l, c), "rsi": wilder_rsi(c), "dem": demarker(h, l), "sma50": sma(c, 50)}
