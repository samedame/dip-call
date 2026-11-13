"""Paper ledger and state. state/state.json holds open positions and per-rule paper equity; ledger/*.csv are append-only logs."""
import csv, json, os

TRADE_COLS = ["rule", "entry_date", "exit_date_plan", "exit_date", "late", "occ", "expiry", "strike", "listed_delta", "contracts", "fraction", "equity_before",
              "bid_in", "ask_in", "spot_in", "model_ask", "ask_over_model", "spread_vs_house", "source_in", "cost", "bid_out", "spot_out", "source_out", "proceeds", "pnl", "ret", "equity_after", "points", "tier", "vix_in", "dd_in", "nfire_in"]
SIGNAL_COLS = ["date", "final", "close", "ibs", "rsi", "dem", "sma50", "dd", "vix", "nfire", "points", "S1", "K1", "K2", "K3", "K4"]
START_EQUITY = 1500.0


def _paths(root):
    return os.path.join(root, "state", "state.json"), os.path.join(root, "ledger", "trades.csv"), os.path.join(root, "ledger", "signals.csv")


def load_state(root):
    p, _, _ = _paths(root)
    if os.path.exists(p):
        with open(p) as f:
            s = json.load(f)
    else:
        s = {}
    s.setdefault("positions", {})
    s.setdefault("equity", {})
    s.setdefault("last", {})
    return s


def save_state(root, s):
    p, _, _ = _paths(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1, sort_keys=True)
    os.replace(tmp, p)


def equity_of(state, rule_id):
    return state["equity"].get(rule_id, START_EQUITY)


def _append(path, cols, row):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def append_trade(root, row):
    _append(_paths(root)[1], TRADE_COLS, row)


def append_signal(root, row):
    """One row per date; a later 'final' row replaces the provisional one."""
    path = _paths(root)[2]
    rows = read_csv(path)
    rows = [r for r in rows if r["date"] != row["date"]]
    rows.append({k: row.get(k, "") for k in SIGNAL_COLS})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SIGNAL_COLS)
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_trades(root):
    return read_csv(_paths(root)[1])


def scorecard(root, rules):
    """Per-rule forward-test numbers next to the backtest's."""
    tr = read_trades(root)
    out = []
    for r in rules:
        x = [t for t in tr if t["rule"] == r.id]
        rets = [float(t["ret"]) for t in x]
        ratios = [float(t["ask_over_model"]) for t in x if t.get("ask_over_model") not in ("", None)]
        out.append(dict(rule=r.id, n=len(x), mean=(sum(rets) / len(rets) if rets else None), win=(sum(1 for v in rets if v > 0) / len(rets) if rets else None),
                        ratio=(sum(ratios) / len(ratios) if ratios else None), bt_mean=r.mean_te, bt_win=r.win_te))
    return out


def scorecard_tiers(root):
    """Closed paper trades of the scored rules (S1, K2) grouped by confidence tier."""
    out = []
    tr = read_trades(root)
    for rid in ("S1", "K2"):
        for tier in ("HIGH", "LOW"):
            x = [float(t["ret"]) for t in tr if t["rule"] == rid and t.get("tier") == tier]
            if x:
                out.append(dict(rule=rid, tier=tier, n=len(x), mean=sum(x) / len(x), win=sum(1 for v in x if v > 0) / len(x)))
    return out
