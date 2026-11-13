"""dip-call-bot runner. Modes: alert (about 15:50 ET: provisional signals, exits, paper entries), confirm (after the close: final signals, void or confirm), status.
Alert-only: nothing here places an order. Every external call goes through Services so tests can replace it."""
import argparse, datetime as dt, os, sys
from dataclasses import dataclass
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import chain as chainmod, data, indicators, ledger, model, nyse, pick, rules, score, sizing
from .notify import post_discord

ET = ZoneInfo("America/New_York")
LABEL = "RESEARCH SIGNAL, NOT ADVICE. Backtest not pre-registered; every historical option price was modelled. The paper ledger is the real-quote test."


@dataclass
class Config:
    root: str = "."
    profile: str = "sustainable"          # "sustainable" (half-Kelly K rules) or "sprint" (champion only)
    account_equity: float = 1500.0
    min_points_real: int = 2              # real-money sizing lines are suppressed for S1/K2 below this many points (paper ledger always records)
    sprint_fraction: float = sizing.SPRINT_DEFAULT
    tradier_token: Optional[str] = None
    tradier_env: Optional[str] = None
    webhook: Optional[str] = None
    force: bool = False
    dry: bool = False


def config_from_env(root="."):
    g = os.environ.get
    return Config(root=root, profile=(g("PROFILE") or "sustainable").lower(), account_equity=float(g("ACCOUNT_EQUITY") or 1500), min_points_real=int(g("MIN_POINTS_REAL") or 2), sprint_fraction=float(g("SPRINT_FRACTION") or sizing.SPRINT_DEFAULT),
                  tradier_token=g("TRADIER_TOKEN") or None, tradier_env=g("TRADIER_ENV") or None, webhook=g("DISCORD_WEBHOOK_URL") or None)


@dataclass
class Services:
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(ET)
    bars: Callable[[], dict] = lambda: data.fetch_bars("SPY", "5y")
    vols: Callable[[], dict] = data.fetch_vols
    chain: Callable[[], tuple] = lambda: chainmod.fetch_cboe("SPY")
    tradier: Optional[Callable[[str], Optional[dict]]] = None     # occ -> dict(bid, ask) or None


def _fmt_d(d):
    return d.strftime("%a %d %b %Y")


def _pct(x):
    return "n/a" if x is None else f"{x * 100:+.0f}%"


def _emit(cfg, text):
    print(text)
    if cfg.webhook and not cfg.dry:
        post_discord(cfg.webhook, text)


def _quote(svc, cfg, row):
    """Bid/ask for one listed contract: Tradier (live) if configured and answering, else the Cboe delayed row."""
    if svc.tradier is not None:
        try:
            q = svc.tradier(row["occ"])
            if q and q["ask"] > 0:
                return q["bid"], q["ask"], "tradier"
        except Exception:  # noqa: BLE001
            pass
    return row["bid"], row["ask"], "cboe-delayed"


def _model_ask(spot, row, today, vols):
    if not vols:
        return None
    try:
        sess = max(1, nyse.sessions_between(today, row["exp"]))
        carry = vols["irx"] / 100 - 0.012
        return model.price_call(spot, row["K"], sess, vols, carry)
    except Exception:  # noqa: BLE001
        return None


def _latest(bars, today):
    if not bars["date"] or bars["date"][-1] != today:
        return None
    ind = indicators.compute(bars)
    sig = rules.rule_signals(ind)
    now = {k: float(v[-1]) for k, v in ind.items()}
    sa = rules.signal_arrays(ind)
    now["dd"] = score.drawdown_last(ind["close"])
    now["nfire"] = score.nfire(sa)
    return ind, {k: bool(v[-1]) for k, v in sig.items()}, now


def _close_position(state, root, pos, rule, row_or_none, svc, cfg, today, spot_out):
    n = pos["contracts"]
    if row_or_none is not None:
        bid, ask, src = _quote(svc, cfg, row_or_none)
    else:
        bid, src = 0.0, "no-quote"
    proceeds = n * (bid * 100 - (pick.FEE if bid > 0 else 0))
    pnl = proceeds - pos["cost"]
    eq_after = pos["equity_before"] + pnl
    state["equity"][rule.id] = eq_after
    trade = dict(pos, exit_date=str(today), late=int(str(today) > pos["exit_date_plan"]), bid_out=round(bid, 4), spot_out=round(spot_out, 2), source_out=src,
                 proceeds=round(proceeds, 2), pnl=round(pnl, 2), ret=round(proceeds / pos["cost"] - 1, 4) if pos["cost"] else 0.0, equity_after=round(eq_after, 2))
    if not cfg.dry:
        ledger.append_trade(cfg.root, trade)
    return trade


def run_alert(svc, cfg):
    now = svc.now()
    today = now.date()
    if not nyse.is_session(today):
        return "not a session"
    state = ledger.load_state(cfg.root)
    close = dt.datetime.combine(today, nyse.close_time(today), ET)
    if not cfg.force:
        if not (close - dt.timedelta(minutes=25) <= now < close):
            return "outside the alert window"
        if state["last"].get("alert") == str(today):
            return "alert already sent today"
    bars = svc.bars()
    cur = _latest(bars, today)
    if cur is None:
        _emit(cfg, f"dip-call-bot {_fmt_d(today)}: Yahoo has no bar for today yet, so no signal check was possible. Run again with --force when it has.")
        return "no bar"
    ind, sig, v = cur
    lines = [f"**dip-call-bot · {_fmt_d(today)} · PROVISIONAL at {now.strftime('%H:%M')} ET** (SPY {v['close']:.2f}, IBS {v['ibs']:.2f}, RSI {v['rsi']:.1f}, DeM {v['dem']:.2f}, SMA50 {v['sma50']:.2f})"]
    if today in nyse.EARLY_CLOSE:
        lines.append("Early close 13:00 ET today: act before 12:55.")
    due = [(rules.BY_ID[rid], p) for rid, p in state["positions"].items() if p["exit_date_plan"] <= str(today)]
    due_ids = {r.id for r, _ in due}
    entering = [r for r in rules.RULES if sig[r.id] and (r.id not in state["positions"] or r.id in due_ids)]
    need_chain = bool(due or entering)
    spot, rows, vols = v["close"], [], None
    if need_chain:
        try:
            spot, rows = svc.chain()
        except Exception as e:  # noqa: BLE001
            lines.append(f"Option chain unavailable ({e}). Signals below are unpriced; nothing was recorded.")
            need_chain = False
            due = []
        try:
            vols = svc.vols()
        except Exception:  # noqa: BLE001
            vols = None
    vix = vols["v30"] if vols else None
    if vix is None:
        try:
            vix = svc.vols()["v30"]
        except Exception:  # noqa: BLE001
            vix = None
    pts = score.points(v["dd"], vix, v["nfire"])
    lines[0] += f" · confidence {('%d/3' % pts) if pts is not None else 'unscored'}"
    # ---- exits first
    for rule, pos in due:
        row = next((r for r in rows if r["occ"] == pos["occ"]), None)
        t = _close_position(state, cfg.root, pos, rule, row, svc, cfg, today, spot)
        del state["positions"][rule.id]
        lines.append(f"**SELL {rule.id}** {pos['contracts']}x {pos['occ']} at the bid {t['bid_out']:.2f} ({t['source_out']}); paper P&L {t['pnl']:+.2f} ({t['ret'] * 100:+.0f}%)" + (" [LATE exit]" if t["late"] else ""))
    # ---- entries
    firing = [r for r in rules.RULES if sig[r.id] and r.id not in state["positions"]]
    sug = sizing.suggested_fractions(firing, cfg.profile, cfg.sprint_fraction)
    for rule in firing:
        if not need_chain:
            lines.append(f"**SIGNAL {rule.id}** {rule.name} (no chain, no quote)")
            continue
        target = nyse.add_sessions(today, rule.tenor)
        row = pick.pick_call(rows, target, rule.delta)
        if row is None:
            lines.append(f"**SIGNAL {rule.id}** {rule.name}: no listed call near delta {rule.delta:.2f} at {target}; skipped.")
            continue
        bid, ask, src = _quote(svc, cfg, row)
        eq = ledger.equity_of(state, rule.id)
        frac = sizing.paper_fraction(rule)
        n = sizing.paper_contracts(eq, frac, ask)
        exit_plan = nyse.add_sessions(today, rule.hold)
        m = _model_ask(spot, row, today, vols)
        ratio = (ask / m) if m else None
        l = [f"**SIGNAL {rule.id}** {rule.name}",
             f"  Contract: SPY {row['exp'].strftime('%d %b %Y')} {row['K']:.0f} call (delta {row['delta']:.2f}); bid {bid:.2f} / ask {ask:.2f} ({src}); spread {row['spread_vs_house']:.1f}x the research's house spread" + (f"; ask is {ratio:.2f}x the research model's price" if ratio else ""),
             f"  Exit: sell at the close on {_fmt_d(exit_plan)} ({rule.hold} session{'s' if rule.hold > 1 else ''}); the alert at 15:50 ET that day will show the bid."]
        ctext, ctier = score.describe(rule.id, pts, v["dd"], vix if vix is not None else float("nan"), v["nfire"])
        l.append(ctext)
        if n > 0:
            cost = n * (ask * 100 + pick.FEE)
            state["positions"][rule.id] = dict(rule=rule.id, entry_date=str(today), exit_date_plan=str(exit_plan), occ=row["occ"], expiry=str(row["exp"]), strike=row["K"], listed_delta=row["delta"],
                                               contracts=n, fraction=round(frac, 4), equity_before=round(eq, 2), bid_in=bid, ask_in=ask, spot_in=round(spot, 2), model_ask=(round(m, 4) if m else ""),
                                               ask_over_model=(round(ratio, 3) if ratio else ""), spread_vs_house=round(row["spread_vs_house"], 2), source_in=src, cost=round(cost, 2), status="provisional",
                                               points=("" if pts is None else pts), tier=ctier, vix_in=("" if vix is None else round(vix, 2)), dd_in=round(v["dd"], 4), nfire_in=v["nfire"])
            l.append(f"  Paper trade: {n:g} contract-equivalents for ${cost:,.0f} ({frac * 100:.1f}% of paper equity ${eq:,.0f}, fractional sizing as in the research); recorded provisionally until the close.")
        else:
            l.append(f"  Paper trade skipped: paper equity ${eq:,.0f} x {frac * 100:.1f}% buys nothing at {ask:.2f}.")
        if rule.id in sug and rule.id in score.SCORED and (pts is None or pts < cfg.min_points_real):
            l.append(f"  If you trade this: NOT suggested. {rule.id} below {cfg.min_points_real} confidence points was the losing side of the backtest ({'unscored' if pts is None else str(pts) + ' point' + ('s' if pts != 1 else '')}); the paper ledger still records it so the score gets tested. Set MIN_POINTS_REAL=0 to see sizing anyway.")
        elif rule.id in sug:
            ns = sizing.contracts(cfg.account_equity, sug[rule.id], ask)
            one = ask * 100 + pick.FEE
            l.append(f"  If you trade this: profile '{cfg.profile}' suggests {sug[rule.id] * 100:.1f}% of ${cfg.account_equity:,.0f} = {ns} whole contract{'s' if ns != 1 else ''}"
                     + (f"; 1 contract costs ${one:,.0f} = {one / cfg.account_equity * 100:.0f}% of the account, more than the suggested share, so this account is too small for the sustainable sizing here" if ns == 0 else "")
                     + (" (ALL-IN lottery sizing: the research's median outcome at this size is $174 left from $1,500)" if cfg.profile == "sprint" else ""))
        lines.append("\n".join(l))
    if not firing and not due:
        lines.append("No rule is firing and no position is due.")
    lines.append(f"Backtest context: {LABEL}")
    state["last"]["alert"] = str(today)
    if not cfg.dry:
        ledger.save_state(cfg.root, state)
    _emit(cfg, "\n".join(lines))
    return "ok"


def run_confirm(svc, cfg):
    now = svc.now()
    today = now.date()
    if not nyse.is_session(today):
        return "not a session"
    state = ledger.load_state(cfg.root)
    close = dt.datetime.combine(today, nyse.close_time(today), ET)
    if not cfg.force:
        if now < close + dt.timedelta(minutes=5):
            return "too early to confirm"
        if state["last"].get("confirm") == str(today):
            return "confirm already sent today"
    bars = svc.bars()
    cur = _latest(bars, today)
    if cur is None:
        _emit(cfg, f"dip-call-bot {_fmt_d(today)}: no final bar yet; confirmation postponed.")
        return "no bar"
    ind, sig, v = cur
    lines = [f"**dip-call-bot · {_fmt_d(today)} · FINAL** (SPY {v['close']:.2f}, IBS {v['ibs']:.2f}, RSI {v['rsi']:.1f}, DeM {v['dem']:.2f}, SMA50 {v['sma50']:.2f})"]
    lines.append("Signals at the close: " + ", ".join(f"{r.id} {'YES' if sig[r.id] else 'no'}" for r in rules.RULES))
    try:
        vix = svc.vols()["v30"]
    except Exception:  # noqa: BLE001
        vix = None
    pts = score.points(v["dd"], vix, v["nfire"])
    lines.append(f"Confidence points at the close: {('%d/3' % pts) if pts is not None else 'unscored'} (SPY {v['dd'] * 100:+.1f}% from 52-week high, VIX {('%.1f' % vix) if vix is not None else 'n/a'}, {v['nfire']} signals firing)")
    for rid in list(state["positions"]):
        p = state["positions"][rid]
        if p["entry_date"] == str(today) and p.get("status") == "provisional":
            if sig[rid]:
                p["status"] = "confirmed"
                if pts is not None:
                    if str(p.get("points", "")) != str(pts):
                        lines.append(f"{rid}: confidence moved from {p.get('points', 'unscored')} to {pts} points with the final close; the ledger keeps the final value.")
                    p["points"], p["tier"] = pts, score.tier(rid, pts)
                    p["vix_in"], p["dd_in"], p["nfire_in"] = round(vix, 2), round(v["dd"], 4), v["nfire"]
                lines.append(f"{rid}: signal held at the close; paper entry confirmed ({p['contracts']}x {p['occ']}).")
            else:
                del state["positions"][rid]
                lines.append(f"{rid}: signal did NOT hold at the close; paper entry VOIDED, nothing counted.")
    missed = [r.id for r in rules.RULES if sig[r.id] and r.id not in state["positions"] and state["last"].get("alert") != str(today)]
    if missed:
        lines.append(f"Signals that fired but were not alerted (alert run missed): {', '.join(missed)}. No paper entry (no quote was captured).")
    row = dict(date=str(today), final=1, close=round(v["close"], 2), ibs=round(v["ibs"], 3), rsi=round(v["rsi"], 2), dem=round(v["dem"], 3), sma50=round(v["sma50"], 2), dd=round(v["dd"], 4), vix=("" if vix is None else round(vix, 2)), nfire=v["nfire"], points=("" if pts is None else pts), **{r.id: int(sig[r.id]) for r in rules.RULES})
    if not cfg.dry:
        ledger.append_signal(cfg.root, row)
    sc = ledger.scorecard(cfg.root, rules.RULES)
    lines.append("Forward test (paper, real quotes) vs backtest mean/win:")
    for s in sc:
        lines.append(f"  {s['rule']}: {s['n']} closed, mean {_pct(s['mean'])}, win {_pct(s['win']).replace('+', '')}, ask/model {('n/a' if s['ratio'] is None else format(s['ratio'], '.2f') + 'x')} | backtest {_pct(s['bt_mean'])}, {s['bt_win'] * 100:.0f}% win | paper equity ${ledger.equity_of(state, s['rule']):,.0f}")
    tiers = ledger.scorecard_tiers(cfg.root)
    if tiers:
        lines.append("Forward test by confidence tier (S1 and K2 only; backtest 2014-2026 in brackets):")
        for t in tiers:
            bt = score.CAL[t["rule"]]["TE"]
            hi = [bt[k] for k in bt if k >= score.HIGH_MIN]; lo = [bt[k] for k in bt if k < score.HIGH_MIN]
            ref = lambda g: (sum(x[0] * x[2] for x in g) / sum(x[2] for x in g), sum(x[1] * x[2] for x in g) / sum(x[2] for x in g)) if g else (None, None)
            m, w = ref(hi if t["tier"] == "HIGH" else lo)
            lines.append(f"  {t['rule']} {t['tier']}: {t['n']} closed, mean {_pct(t['mean'])}, win {_pct(t['win']).replace('+', '')}" + (f" [{m * 100:+.0f}%, {w * 100:.0f}% win]" if m is not None else ""))
    open_pos = [f"{p['rule']} exits {p['exit_date_plan']}" for p in state["positions"].values()]
    lines.append("Open paper positions: " + (", ".join(open_pos) if open_pos else "none"))
    state["last"]["confirm"] = str(today)
    if not cfg.dry:
        ledger.save_state(cfg.root, state)
    _emit(cfg, "\n".join(lines))
    return "ok"


def run_status(svc, cfg):
    state = ledger.load_state(cfg.root)
    print("Open positions:", state["positions"] or "none")
    for s in ledger.scorecard(cfg.root, rules.RULES):
        print(s)
    return "ok"


def main(argv=None, svc=None):
    ap = argparse.ArgumentParser(prog="dip-call-bot")
    ap.add_argument("mode", choices=["alert", "confirm", "auto", "status"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true", help="print only: no Discord, no ledger or state writes")
    a = ap.parse_args(argv)
    cfg = config_from_env(a.root)
    cfg.force, cfg.dry = a.force, a.dry
    svc = svc or Services()
    if cfg.tradier_token and svc.tradier is None:
        svc.tradier = lambda occ: chainmod.tradier_quotes([occ], cfg.tradier_token, cfg.tradier_env).get(occ)
    mode = a.mode
    if mode == "auto":
        n = svc.now()
        if not nyse.is_session(n.date()):
            print("not a session"); return 0
        close = dt.datetime.combine(n.date(), nyse.close_time(n.date()), ET)
        mode = "alert" if n < close else "confirm"
    res = {"alert": run_alert, "confirm": run_confirm, "status": run_status}[mode](svc, cfg)
    print(f"[{mode}] {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
