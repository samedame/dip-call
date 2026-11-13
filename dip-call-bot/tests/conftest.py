import csv, datetime as dt, json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from zoneinfo import ZoneInfo
from bot import chain as chainmod, rules, run

FX = os.path.join(os.path.dirname(__file__), "fixtures")
ET = ZoneInfo("America/New_York")


def load_bars(until="2026-11-12"):
    rows = list(csv.DictReader(open(os.path.join(FX, "SPY_daily.csv"))))
    rows = [r for r in rows if r["date"] <= until]
    return {"date": [dt.date.fromisoformat(r["date"]) for r in rows], "o": [float(r["open"]) for r in rows], "h": [float(r["high"]) for r in rows],
            "l": [float(r["low"]) for r in rows], "c": [float(r["close"]) for r in rows], "v": [float(r["volume"]) for r in rows]}


def weak_last(bars, close=700.0):
    """Turn the last bar into a deep weak close so IBS, SMA50 (and usually RSI) rules fire."""
    b = {k: list(v) for k, v in bars.items()}
    b["o"][-1], b["h"][-1], b["l"][-1], b["c"][-1] = 755.0, 760.0, close - 1, close
    return b


def add_day(bars, date, o, h, l, c):
    b = {k: list(v) for k, v in bars.items()}
    for k, v in (("date", date), ("o", o), ("h", h), ("l", l), ("c", c), ("v", 1.0)):
        b[k].append(v)
    return b


@pytest.fixture
def chain_rows():
    return chainmod.parse_cboe(json.load(open(os.path.join(FX, "spy_chain_20261112.json"))))


VOLS = dict(v1=15.99, v9=17.51, v30=18.70, v93=20.06, irx=4.128)


def make_svc(now, bars, chain, tradier=None, vols=VOLS):
    spot, rows = chain
    return run.Services(now=lambda: now, bars=lambda: bars, vols=lambda: dict(vols), chain=lambda: (spot, rows), tradier=tradier)


def et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)
