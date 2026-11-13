"""Option quotes: Cboe delayed chain (free, ~15 minutes late) for contract selection; optional Tradier for a live bid/ask of the picked contract."""
import datetime as dt
import re
import requests

CBOE = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
_OCC = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")


def parse_cboe(payload, root="SPY"):
    """-> (spot, rows). rows: dict(occ, exp, cp, K, bid, ask, iv, delta, oi, vol). Non-standard roots (e.g. B1SPY) are ignored."""
    d = payload["data"]
    spot = d.get("current_price") or d.get("close")
    pat = re.compile(rf"^{root}(\d{{6}})([CP])(\d{{8}})$")
    rows = []
    for o in d["options"]:
        m = pat.match(o["option"])
        if not m:
            continue
        e = m.group(1)
        rows.append(dict(occ=o["option"], exp=dt.date(2000 + int(e[:2]), int(e[2:4]), int(e[4:6])), cp=m.group(2), K=int(m.group(3)) / 1000.0,
                         bid=float(o.get("bid") or 0), ask=float(o.get("ask") or 0), iv=float(o.get("iv") or 0), delta=float(o.get("delta") or 0),
                         oi=float(o.get("open_interest") or 0), vol=float(o.get("volume") or 0)))
    return float(spot), rows


def fetch_cboe(root="SPY"):
    last = None
    for _ in range(3):
        try:
            r = requests.get(CBOE.format(root), timeout=60)
            r.raise_for_status()
            return parse_cboe(r.json(), root)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Cboe chain fetch failed: {last}")


def tradier_base(env):
    return "https://sandbox.tradier.com/v1" if (env or "").lower() == "sandbox" else "https://api.tradier.com/v1"


def tradier_quotes(symbols, token, env=None):
    """Read-only quote endpoint. Returns {symbol: dict(bid, ask, last, iv, delta)}. Raises on HTTP errors."""
    r = requests.get(tradier_base(env) + "/markets/quotes", params={"symbols": ",".join(symbols), "greeks": "true"},
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    q = (r.json().get("quotes") or {}).get("quote")
    if q is None:
        return {}
    if isinstance(q, dict):
        q = [q]
    out = {}
    for x in q:
        g = x.get("greeks") or {}
        out[x["symbol"]] = dict(bid=float(x.get("bid") or 0), ask=float(x.get("ask") or 0), last=x.get("last"), iv=g.get("mid_iv"), delta=g.get("delta"))
    return out


def occ_symbol(root, exp, cp, K):
    return f"{root}{exp.strftime('%y%m%d')}{cp}{int(round(K * 1000)):08d}"
