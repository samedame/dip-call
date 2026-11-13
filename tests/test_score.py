import csv, datetime as dt, os
import numpy as np
from bot import indicators, ledger, rules, run, score
from tests.conftest import load_bars, weak_last, add_day, make_svc, et, FX, VOLS

D = dt.date


def test_points_match_research_on_every_day():
    rows = list(csv.DictReader(open(os.path.join(FX, "SPY_daily.csv"))))
    dates = [r["date"] for r in rows]
    bars = {"date": dates, **{k: np.array([float(r[n]) for r in rows]) for k, n in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}}
    ind = indicators.compute(bars)
    sa = rules.signal_arrays(ind)
    dd = score.drawdown(ind["close"])
    pos = {d: i for i, d in enumerate(dates)}
    exp = list(csv.DictReader(open(os.path.join(FX, "expected_score.csv"))))
    bad = n = 0
    for k, r in enumerate(exp):
        if k < 300:          # the research series starts ~210 bars after SPY's first bar; its rolling window differs until it fills
            continue
        i = pos[r["date"]]
        nf = score.nfire(sa, i)
        assert nf == int(r["nfire"])
        assert abs(dd[i] - float(r["dd"])) < 1e-9
        p = score.points(dd[i], float(r["vix"]), nf)
        n += 1
        bad += p != int(r["pts"])
    assert n > 7900 and bad == 0


def test_drawdown_last_equals_series_and_points_edges():
    rows = list(csv.DictReader(open(os.path.join(FX, "SPY_daily.csv"))))
    c = np.array([float(r["close"]) for r in rows])
    assert abs(score.drawdown_last(c) - score.drawdown(c)[-1]) < 1e-12
    assert score.points(-0.051, 22.01, 2) == 3 and score.points(-0.05, 22.0, 1) == 0 and score.points(-0.1, None, 2) is None
    assert score.tier("S1", 2) == "HIGH" and score.tier("K2", 1) == "LOW" and score.tier("K1", 3) == "N/A" and score.tier("S1", None) == "UNSCORED"


def test_describe_texts():
    t, tier = score.describe("S1", 1, -0.037, 20.4, 2)
    assert tier == "LOW" and "-3%" in t and "Not a win probability" in t
    t, tier = score.describe("K1", 3, -0.1, 25, 3)
    assert tier == "N/A" and "did not separate" in t


def test_alert_high_tier_entry_is_logged_with_points(tmp_path, chain_rows, capsys):
    bars = weak_last(load_bars())                      # close 700 vs 52w high ~779 -> -10%; 3 signals fire
    c = run.Config(root=str(tmp_path), dry=False)
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c)
    out = capsys.readouterr().out
    assert "confidence 2/3" in out and "tier HIGH" in out and "-3%" not in out.split("SIGNAL S1")[1].split("SIGNAL K1")[0]
    st = ledger.load_state(str(tmp_path))
    assert st["positions"]["S1"]["points"] == 2 and st["positions"]["S1"]["tier"] == "HIGH" and st["positions"]["K1"]["tier"] == "N/A"
    assert "NOT suggested" not in out


def test_low_tier_suppresses_real_money_line_but_paper_still_records(tmp_path, chain_rows, capsys):
    bars = weak_last(load_bars())
    bars["c"][-1] = 745.0; bars["l"][-1] = 744.0       # only 4.4% below the high, IBS low: S1 fires, dd above -5% threshold
    c = run.Config(root=str(tmp_path), dry=False, profile="sprint")
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c)
    out = capsys.readouterr().out
    st = ledger.load_state(str(tmp_path))
    pts = st["positions"]["S1"]["points"]
    assert pts <= 1 and st["positions"]["S1"]["tier"] == "LOW"
    assert "NOT suggested" in out and "ALL-IN" not in out
    # config override shows the sizing anyway
    c2 = run.Config(root=str(tmp_path / "b"), dry=False, profile="sprint", min_points_real=0)
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c2)
    assert "ALL-IN" in capsys.readouterr().out


def test_vix_outage_gives_unscored_not_a_crash(tmp_path, chain_rows, capsys):
    svc = make_svc(et(2026, 11, 12, 15, 50), weak_last(load_bars()), chain_rows)
    def bad(): raise RuntimeError("yahoo")
    svc.vols = bad
    assert run.run_alert(svc, run.Config(root=str(tmp_path), dry=False)) == "ok"
    out = capsys.readouterr().out
    assert "unscored" in out and ledger.load_state(str(tmp_path))["positions"]["S1"]["tier"] == "UNSCORED"


def test_confirm_updates_points_and_tier_scorecard(tmp_path, chain_rows, capsys):
    bars = weak_last(load_bars())
    c = run.Config(root=str(tmp_path), dry=False)
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c)
    svc = make_svc(et(2026, 11, 12, 16, 25), bars, chain_rows, vols=dict(VOLS, v30=26.0))      # VIX closed higher: +1 point
    run.run_confirm(svc, c)
    out = capsys.readouterr().out
    assert "confidence moved from 2 to 3" in out
    assert ledger.load_state(str(tmp_path))["positions"]["S1"]["points"] == 3
    sig = ledger.read_csv(os.path.join(str(tmp_path), "ledger", "signals.csv"))
    assert sig[0]["points"] == "3" and sig[0]["vix"] == "26.0"
    b13 = add_day(bars, D(2026, 11, 13), 700, 712, 698, 710); b16 = add_day(b13, D(2026, 11, 16), 710, 716, 705, 714)
    run.run_alert(make_svc(et(2026, 11, 13, 15, 50), b13, chain_rows), c)
    run.run_alert(make_svc(et(2026, 11, 16, 15, 50), b16, chain_rows), c)
    tiers = ledger.scorecard_tiers(str(tmp_path))
    assert {(t["rule"], t["tier"]) for t in tiers} >= {("S1", "HIGH"), ("K2", "HIGH")}
    run.run_confirm(make_svc(et(2026, 11, 16, 16, 25), b16, chain_rows), c)
    assert "Forward test by confidence tier" in capsys.readouterr().out
