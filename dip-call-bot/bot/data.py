"""Yahoo daily bars and index levels. Yahoo's chart endpoint returns today's partial bar while the market is open."""
import datetime as dt
import requests

UA = {"User-Agent": "Mozilla/5.0"}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


def _get(sym, **params):
    last = None
    for _ in range(3):
        try:
            r = requests.get(URL.format(sym), params=params, headers=UA, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            return res
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Yahoo fetch failed for {sym}: {last}")


def fetch_bars(sym="SPY", rng="5y"):
    """Daily bars as dict(date,o,h,l,c,v) with dates as date objects in exchange time. Bars with a null close are dropped."""
    res = _get(sym, range=rng, interval="1d")
    off = res["meta"].get("gmtoffset", -18000)
    q = res["indicators"]["quote"][0]
    out = {k: [] for k in ("date", "o", "h", "l", "c", "v")}
    for i, t in enumerate(res["timestamp"]):
        if q["close"][i] is None or q["open"][i] is None or q["high"][i] is None or q["low"][i] is None:
            continue
        d = (dt.datetime.fromtimestamp(t, dt.timezone.utc) + dt.timedelta(seconds=off)).date()
        out["date"].append(d)
        for k, kk in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume")):
            out[k].append(q[kk][i])
    return out


def last_level(sym):
    res = _get(sym, range="5d", interval="1d")
    p = res["meta"].get("regularMarketPrice")
    if p is None:
        cl = [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
        p = cl[-1]
    return float(p)


def fetch_vols():
    """VIX1D, VIX9D, VIX, VIX3M in index points and the 13-week bill rate in percent."""
    return dict(v1=last_level("^VIX1D"), v9=last_level("^VIX9D"), v30=last_level("^VIX"), v93=last_level("^VIX3M"), irx=last_level("^IRX"))
