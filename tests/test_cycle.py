"""Full-day cycles with fake services and a fake clock: alert -> confirm -> exit alert, restart, void, late exit, idempotency, Discord chunks."""
import datetime as dt, json, os
import pytest
from bot import ledger, rules, run, nyse
from tests.conftest import load_bars, weak_last, add_day, make_svc, et, VOLS

D = dt.date


def cfg(tmp, **kw):
    return run.Config(root=str(tmp), dry=False, **kw)


def firing_today(bars):
    from bot import indicators
    return [k for k, v in rules.rule_signals(indicators.compute(bars)).items() if v[-1]]


def test_alert_confirm_exit_cycle_with_restart(tmp_path, chain_rows, capsys):
    bars = weak_last(load_bars())                         # 12 Nov 2026 with a deep weak close
    fire = firing_today(bars)
    assert "S1" in fire and "K1" in fire and "K2" in fire
    c = cfg(tmp_path)
    # ---- 15:50 alert
    assert run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c) == "ok"
    out = capsys.readouterr().out
    assert "PROVISIONAL" in out and all(f"SIGNAL {r}" in out for r in fire)
    st = ledger.load_state(str(tmp_path))
    assert set(st["positions"]) == set(fire) and st["last"]["alert"] == "2026-11-12"
    for rid, p in st["positions"].items():
        r = rules.BY_ID[rid]
        assert p["status"] == "provisional" and p["exit_date_plan"] == str(nyse.add_sessions(D(2026, 11, 12), r.hold))
        assert p["contracts"] > 0 and p["cost"] > 0 and p["occ"].startswith("SPY") and p["ask_over_model"] != ""
    # ---- second alert the same day is ignored
    assert run.run_alert(make_svc(et(2026, 11, 12, 15, 55), bars, chain_rows), c) == "alert already sent today"
    # ---- outside the window
    assert run.run_alert(make_svc(et(2026, 11, 12, 11, 0), bars, chain_rows), cfg(tmp_path / "other")) == "outside the alert window"
    # ---- confirm: signal holds
    assert run.run_confirm(make_svc(et(2026, 11, 12, 16, 25), bars, chain_rows), c) == "ok"
    st = ledger.load_state(str(tmp_path))
    assert all(p["status"] == "confirmed" for p in st["positions"].values())
    sig_rows = ledger.read_csv(os.path.join(str(tmp_path), "ledger", "signals.csv"))
    assert len(sig_rows) == 1 and sig_rows[0]["final"] == "1" and int(sig_rows[0]["S1"]) == 1
    assert run.run_confirm(make_svc(et(2026, 11, 12, 16, 30), bars, chain_rows), c) == "confirm already sent today"
    # ---- restart: next sessions Fri 13 (K3/K4 hold 1) and Mon 16 (hold 2). Reload from disk only.
    b13 = add_day(bars, D(2026, 11, 13), 700, 712, 698, 710)
    assert run.run_alert(make_svc(et(2026, 11, 13, 15, 50), b13, chain_rows), c) == "ok"
    st = ledger.load_state(str(tmp_path))
    closed13 = [r for r in ledger.read_trades(str(tmp_path))]
    assert {t["rule"] for t in closed13} == {k for k in fire if rules.BY_ID[k].hold == 1}
    b16 = add_day(b13, D(2026, 11, 16), 710, 716, 705, 714)
    assert run.run_alert(make_svc(et(2026, 11, 16, 15, 50), b16, chain_rows), c) == "ok"
    trades = ledger.read_trades(str(tmp_path))
    assert {t["rule"] for t in trades} >= {k for k in fire if rules.BY_ID[k].hold == 2}
    st = ledger.load_state(str(tmp_path))
    for t in trades:
        n, cost = float(t["contracts"]), float(t["cost"])
        proceeds = n * (float(t["bid_out"]) * 100 - (0.04 if float(t["bid_out"]) > 0 else 0))
        assert abs(float(t["proceeds"]) - proceeds) < 0.01 and abs(float(t["pnl"]) - (proceeds - cost)) < 0.01
        assert abs(ledger.equity_of(st, t["rule"]) - (float(t["equity_before"]) + float(t["pnl"]))) < 0.02
        assert t["late"] == "0" and t["exit_date"] == t["exit_date_plan"]
    # entry same-day exits free the rule: no open position remains for rules that exited without refiring
    sc = ledger.scorecard(str(tmp_path), rules.RULES)
    assert sum(s["n"] for s in sc) == len(trades)


def test_confirm_voids_entry_when_final_close_loses_signal(tmp_path, chain_rows, capsys):
    prov = weak_last(load_bars())
    final = {k: list(v) for k, v in prov.items()}
    final["c"][-1] = final["h"][-1] - 0.5                  # rallied into the close: IBS ~0.9, above SMA50 region? (K1 may still hold, so only check S1/K2)
    c = cfg(tmp_path)
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), prov, chain_rows), c)
    before = set(ledger.load_state(str(tmp_path))["positions"])
    assert {"S1", "K2"} <= before
    run.run_confirm(make_svc(et(2026, 11, 12, 16, 25), final, chain_rows), c)
    after = ledger.load_state(str(tmp_path))["positions"]
    assert "S1" not in after and "K2" not in after
    assert "VOIDED" in capsys.readouterr().out
    assert ledger.read_trades(str(tmp_path)) == []


def test_late_exit_is_flagged(tmp_path, chain_rows):
    bars = weak_last(load_bars())
    c = cfg(tmp_path)
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows), c)
    b = add_day(add_day(bars, D(2026, 11, 13), 700, 712, 698, 710), D(2026, 11, 16), 710, 716, 705, 714)
    b = add_day(b, D(2026, 11, 17), 714, 720, 712, 718)
    run.run_alert(make_svc(et(2026, 11, 17, 15, 50), b, chain_rows), c)       # skipped 13 and 16 entirely
    tr = ledger.read_trades(str(tmp_path))
    assert tr and all(t["late"] == "1" for t in tr if t["exit_date_plan"] < "2026-11-17")


def test_tradier_quote_overrides_cboe_and_is_recorded(tmp_path, chain_rows):
    bars = weak_last(load_bars())
    svc = make_svc(et(2026, 11, 12, 15, 50), bars, chain_rows, tradier=lambda occ: dict(bid=0.40, ask=0.44, last=0.42, iv=0.1, delta=0.1))
    run.run_alert(svc, cfg(tmp_path))
    pos = ledger.load_state(str(tmp_path))["positions"]
    assert pos and all(p["source_in"] == "tradier" and p["ask_in"] == 0.44 and p["bid_in"] == 0.40 for p in pos.values())


def test_tradier_failure_falls_back_to_cboe(tmp_path, chain_rows):
    def boom(occ): raise RuntimeError("401")
    svc = make_svc(et(2026, 11, 12, 15, 50), weak_last(load_bars()), chain_rows, tradier=boom)
    run.run_alert(svc, cfg(tmp_path))
    assert all(p["source_in"] == "cboe-delayed" for p in ledger.load_state(str(tmp_path))["positions"].values())


def test_chain_outage_does_not_crash_or_record(tmp_path, chain_rows, capsys):
    def bad(): raise RuntimeError("503")
    svc = make_svc(et(2026, 11, 12, 15, 50), weak_last(load_bars()), chain_rows)
    svc.chain = bad
    assert run.run_alert(svc, cfg(tmp_path)) == "ok"
    assert ledger.load_state(str(tmp_path))["positions"] == {} and "Option chain unavailable" in capsys.readouterr().out


def test_no_bar_for_today_and_non_session(tmp_path, chain_rows):
    bars = load_bars()
    assert run.run_alert(make_svc(et(2026, 11, 13, 15, 50), bars, chain_rows), cfg(tmp_path)) == "no bar"
    assert run.run_alert(make_svc(et(2026, 11, 14, 15, 50), bars, chain_rows), cfg(tmp_path)) == "not a session"
    assert run.run_alert(make_svc(et(2026, 11, 26, 15, 50), bars, chain_rows), cfg(tmp_path)) == "not a session"


def test_no_signal_day_is_quiet_and_dry_writes_nothing(tmp_path, chain_rows, capsys):
    bars = load_bars()
    bars = add_day(bars, D(2026, 11, 13), 768, 772, 766, 771.5)      # strong close above the 50-day average
    c = run.Config(root=str(tmp_path), dry=True)
    run.run_alert(make_svc(et(2026, 11, 13, 15, 50), bars, chain_rows), c)
    assert "No rule is firing" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(str(tmp_path), "state", "state.json"))


def test_discord_post_chunks_and_sends(tmp_path, chain_rows, monkeypatch):
    sent = []
    import bot.notify as n
    class R: status_code = 204
    monkeypatch.setattr(n.requests, "post", lambda url, json=None, timeout=None: sent.append(json["content"]) or R())
    c = cfg(tmp_path, webhook="https://discord.test/hook")
    run.run_alert(make_svc(et(2026, 11, 12, 15, 50), weak_last(load_bars()), chain_rows), c)
    assert sent and all(len(s) <= 2000 for s in sent) and any("SIGNAL" in s for s in sent)


def test_early_close_day_window(tmp_path, chain_rows):
    """27 Nov 2026 closes at 13:00 ET: a 12:50 alert is inside the window, 15:50 is not."""
    bars = add_day(load_bars(), D(2026, 11, 27), 757, 762, 756, 761.5)
    assert run.run_alert(make_svc(et(2026, 11, 27, 15, 50), bars, chain_rows), cfg(tmp_path)) == "outside the alert window"
    assert run.run_alert(make_svc(et(2026, 11, 27, 12, 50), bars, chain_rows), cfg(tmp_path)) == "ok"


def test_main_auto_mode_picks_alert_before_close_and_confirm_after(tmp_path, chain_rows, monkeypatch, capsys):
    bars = weak_last(load_bars())
    monkeypatch.setenv("PROFILE", "sprint")
    run.main(["auto", "--root", str(tmp_path), "--dry"], svc=make_svc(et(2026, 11, 12, 15, 52), bars, chain_rows))
    out = capsys.readouterr().out
    assert "[alert] ok" in out and "ALL-IN lottery sizing" in out
    run.main(["auto", "--root", str(tmp_path), "--dry"], svc=make_svc(et(2026, 11, 12, 16, 26), bars, chain_rows))
    assert "[confirm] ok" in capsys.readouterr().out


def test_ping_posts_once_and_writes_nothing(tmp_path, chain_rows, monkeypatch, capsys):
    sent = []
    import bot.notify as n
    class R: status_code = 204
    monkeypatch.setattr(n.requests, "post", lambda url, json=None, timeout=None: sent.append(json["content"]) or R())
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    assert run.main(["ping", "--root", str(tmp_path)], svc=make_svc(et(2026, 11, 13, 12, 0), load_bars(), chain_rows)) == 0
    assert len(sent) == 1 and "ping" in sent[0] and "Cboe chain: OK" in sent[0] and "13:50 MT" in sent[0]
    assert not os.path.exists(os.path.join(str(tmp_path), "state", "state.json")) and not os.path.exists(os.path.join(str(tmp_path), "ledger", "trades.csv"))
