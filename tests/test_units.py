import datetime as dt, json, os
import pytest
from bot import chain as chainmod, nyse, pick, sizing, rules, model, ledger

FX = os.path.join(os.path.dirname(__file__), "fixtures")
D = dt.date


def test_calendar_skips_holidays_and_weekends():
    assert nyse.add_sessions(D(2026, 11, 25), 1) == D(2026, 11, 27)      # Thanksgiving 26 Nov closed
    assert nyse.add_sessions(D(2026, 11, 12), 2) == D(2026, 11, 16)      # Fri 13, then Mon 16
    assert nyse.add_sessions(D(2026, 12, 23), 2) == D(2026, 12, 28)      # 24 Dec early close (open), 25 Dec closed
    assert not nyse.is_session(D(2026, 12, 25)) and not nyse.is_session(D(2026, 11, 14))
    assert nyse.sessions_between(D(2026, 11, 12), D(2026, 11, 19)) == 5
    assert nyse.close_time(D(2026, 11, 27)) == dt.time(13, 0)
    with pytest.raises(nyse.CalendarExpired):
        nyse.is_session(D(2028, 1, 4))


def test_chain_parse_ignores_nonstandard_roots(chain_rows):
    spot, rows = chain_rows
    assert abs(spot - 757.12) < 1e-9
    assert rows and all(r["occ"].startswith("SPY2") for r in rows)
    assert not any("B1SPY" in r["occ"] for r in rows)


def test_pick_each_rule_is_near_target_delta_and_expiry(chain_rows):
    spot, rows = chain_rows
    today = D(2026, 11, 12)
    for r in rules.RULES:
        target = nyse.add_sessions(today, r.tenor)
        c = pick.pick_call(rows, target, r.delta)
        assert c is not None, r.id
        assert c["exp"] >= target and (c["exp"] - target).days <= 4
        assert abs(c["delta"] - r.delta) < 0.04 and c["bid"] > 0 and c["ask"] >= c["bid"]


def test_market_vs_model_on_the_live_chain(chain_rows):
    """The research's pricing weak point, measured on real quotes (12 Nov close, 17 priced contracts). Model within a wide band of the ask."""
    spot, rows = chain_rows
    today = D(2026, 11, 12)
    vols = dict(v1=15.99, v9=17.51, v30=18.70, v93=20.06)
    ratios = {}
    for r in rules.RULES:
        c = pick.pick_call(rows, nyse.add_sessions(today, r.tenor), r.delta)
        sess = nyse.sessions_between(today, c["exp"])
        m = model.price_call(spot, c["K"], sess, vols, 0.04128 - 0.012)
        ratios[r.id] = c["ask"] / m
    print("ask / research model price on 12 Nov 2026 close:", {k: round(v, 2) for k, v in ratios.items()})
    for v in ratios.values():
        assert 0.5 < v < 2.0


def test_sizing_whole_contracts_and_cap():
    assert sizing.contracts(1500, 0.10, 0.35) == 4                        # 150 / (35.04)
    assert sizing.contracts(1500, 0.10, 2.0) == 0
    assert abs(sizing.paper_contracts(1500, 0.05, 1.07) - 0.7) < 0.01 and sizing.paper_contracts(0, 0.1, 1) == 0
    firing = [r for r in rules.RULES if r.family == "kelly"]
    f = sizing.suggested_fractions(firing, "sustainable")
    assert abs(sum(f.values()) - 0.35) < 1e-9 and set(f) == {"K1", "K2", "K3", "K4"}
    assert sizing.suggested_fractions(rules.RULES, "sprint", 0.75) == {"S1": 0.75}
    one = sizing.suggested_fractions([rules.BY_ID["K2"]], "sustainable")
    assert abs(one["K2"] - 0.155) < 1e-9


def test_tradier_quote_parsing_with_mock(monkeypatch):
    calls = {}

    class R:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.update(url=url, params=params, headers=headers)
        return R({"quotes": {"quote": {"symbol": "SPY261120C00785000", "bid": 0.31, "ask": 0.33, "last": 0.32, "greeks": {"mid_iv": 0.12, "delta": 0.07}}}})

    monkeypatch.setattr(chainmod.requests, "get", fake_get)
    q = chainmod.tradier_quotes(["SPY261120C00785000"], "tok", "sandbox")
    assert q["SPY261120C00785000"] == dict(bid=0.31, ask=0.33, last=0.32, iv=0.12, delta=0.07)
    assert calls["url"].startswith("https://sandbox.tradier.com") and calls["headers"]["Authorization"] == "Bearer tok"
    assert chainmod.occ_symbol("SPY", D(2026, 11, 20), "C", 785) == "SPY261120C00785000"


def test_ledger_roundtrip_and_signal_row_replaced(tmp_path):
    root = str(tmp_path)
    s = ledger.load_state(root)
    assert s["positions"] == {} and ledger.equity_of(s, "K1") == 1500.0
    s["equity"]["K1"] = 1620.0
    ledger.save_state(root, s)
    assert ledger.equity_of(ledger.load_state(root), "K1") == 1620.0
    ledger.append_signal(root, dict(date="2026-11-12", final=0, close=1))
    ledger.append_signal(root, dict(date="2026-11-12", final=1, close=2))
    rows = ledger.read_csv(os.path.join(root, "ledger", "signals.csv"))
    assert len(rows) == 1 and rows[0]["final"] == "1" and rows[0]["close"] == "2"
