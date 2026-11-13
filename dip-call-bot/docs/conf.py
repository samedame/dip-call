import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from engine import *
from tournament import sigs_close
def net(p, v, cm):
    pin = p + half_spread(p, cm, 1) + FEE/100; vo = np.maximum(v - np.where(v > 0, half_spread(v, cm, 1) + FEE/100, 0), 0); return vo/pin - 1
u = U("SPY"); d = u.df; sc = sigs_close(u); split = pd.Timestamp("2014-01-01")
era = u.dates >= pd.Timestamp("2001-12-01"); tr = era & (u.dates < split); te = u.dates >= split
hi = d.close.rolling(252, min_periods=120).max()
F = pd.DataFrame({"dd": (d.close/hi - 1).values, "vix": d.vix.values, "ibs": d.ibs.values, "rsi": d.rsi.values, "ret5": d.ret5.values, "ret1": d.ret1.values,
                  "a200": (d.close/d.sma200 - 1).values, "a50": (d.close/d.sma50 - 1).values, "term": (d.v9/d.vix).values,
                  "nfire": (sc["IBS20"].astype(int) + sc["TRENDDN"] + sc["IBS10"] + sc["DIP2"])})
RULES = [("S1","IBS20",.07,5,2),("K1","TRENDDN",.15,5,2),("K2","IBS10",.30,10,2),("K3","DIP2",.15,2,1),("K4","DIP2",.30,2,1)]
R = {}
for rid, sig, delta, ten, hold in RULES:
    p, v, K = u.multi_struct("C", delta, ten, hold); r = net(p, v, u.cm); ok = np.isfinite(r) & sc[sig] & F.notna().all(axis=1).values
    keep = np.zeros(u.N, bool); nxt = 0
    for i in np.where(ok)[0]:
        if i >= nxt: keep[i] = True; nxt = i + hold
    # underlying move over the hold (model-free check)
    j = np.minimum(np.arange(u.N) + hold, u.N-1); und = u.c[j]/u.c - 1
    R[rid] = (keep, r, und)
rng = np.random.default_rng(1)
def boot(a, b, n=4000):
    if len(a) < 8 or len(b) < 8: return np.nan
    x = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)]); return (x > 0).mean()
print("=== 1. Single features: terciles cut on 2001-2013, applied to 2014-2026. mean return / win rate per tercile (low, mid, high value of the feature)")
rows = []
for rid in R:
    keep, r, und = R[rid]
    for f in F.columns:
        x = F[f].values; a = keep & tr; b = keep & te
        if f == "nfire": cuts = [1.5, 2.5]
        else: cuts = np.quantile(x[a], [1/3, 2/3])
        def tab(m):
            g = np.digitize(x[m], cuts); return [(r[m][g == k].mean() if (g == k).sum() else np.nan, (r[m][g == k] > 0).mean() if (g == k).sum() else np.nan, (g == k).sum(), und[m][g == k].mean() if (g == k).sum() else np.nan) for k in range(3)]
        A, B = tab(a), tab(b)
        dtr = A[2][0] - A[0][0]; dte = B[2][0] - B[0][0]
        g = np.digitize(x[b], cuts); pb = boot(r[b][g == 2], r[b][g == 0]) if dtr > 0 else boot(r[b][g == 0], r[b][g == 2])
        rows.append(dict(rule=rid, feat=f, tr_lo=A[0][0], tr_mid=A[1][0], tr_hi=A[2][0], te_lo=B[0][0], te_mid=B[1][0], te_hi=B[2][0], te_win_lo=B[0][1], te_win_hi=B[2][1], n_te_lo=B[0][2], n_te_hi=B[2][2],
                         und_te_lo=B[0][3]*100, und_te_hi=B[2][3]*100, same_sign=np.sign(dtr) == np.sign(dte), p_boot_te=pb))
T = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(T.round(3).to_string(index=False))
print("\nshare of (rule, feature) pairs where the high-minus-low spread kept its sign out of sample:", T.same_sign.mean().round(2), "of", len(T), "| pairs with bootstrap p > 0.95 in test:", int((T.p_boot_te > 0.95).sum()))
T.to_pickle("conf_single.pkl")
print("\n=== 2. Composite score: ridge regression of log(1+clipped return) and logistic win model on z-scored features, fit 2001-2013, scored 2014-2026")
feats = ["dd", "vix", "ibs", "rsi", "ret5", "a200", "term", "nfire"]
out = []
for rid in R:
    keep, r, und = R[rid]; a = keep & tr; b = keep & te
    X = F[feats].values; mu, sd = X[a].mean(0), X[a].std(0) + 1e-9; Z = (X - mu)/sd
    y = np.clip(r, -1, 5)                       # clip the lottery tail so one trade does not set the fit
    lam = 10.0; A_ = np.column_stack([np.ones(a.sum()), Z[a]]); w = np.linalg.solve(A_.T @ A_ + lam*np.eye(A_.shape[1]), A_.T @ y[a])
    s = np.column_stack([np.ones(u.N), Z]) @ w
    cuts = np.quantile(s[a], [1/3, 2/3]); g = np.digitize(s[b], cuts); ga = np.digitize(s[a], cuts)
    rb = r[b]; ra = r[a]
    from scipy.stats import spearmanr
    rho, pv = spearmanr(s[b], rb)
    out.append(dict(rule=rid, n_te=int(b.sum()), tr_lo=ra[ga == 0].mean(), tr_hi=ra[ga == 2].mean(), te_lo=rb[g == 0].mean(), te_mid=rb[g == 1].mean(), te_hi=rb[g == 2].mean(),
                    win_lo=(rb[g == 0] > 0).mean(), win_mid=(rb[g == 1] > 0).mean(), win_hi=(rb[g == 2] > 0).mean(), n_lo=int((g == 0).sum()), n_hi=int((g == 2).sum()),
                    spearman=rho, p=pv, p_boot=boot(rb[g == 2], rb[g == 0])))
C = pd.DataFrame(out); print(C.round(3).to_string(index=False)); C.to_pickle("conf_comp.pkl")
print("\n=== 3. One pre-specified, simple score (no fitting): points = [SPY >5% below 52w high] + [VIX > 22] + [2+ rules firing]. 2001-2013 vs 2014-2026")
pts = (F.dd.values < -0.05).astype(int) + (F.vix.values > 22) + (F.nfire.values >= 2)
for rid in R:
    keep, r, und = R[rid]
    line = [rid]
    for nm, m in (("TR", keep & tr), ("TE", keep & te)):
        for k in range(4):
            x = r[m & (pts == k)]; line.append(f"{nm} {k}pt n={len(x)} mean={x.mean()*100:+.0f}% win={(x > 0).mean()*100:.0f}% und={und[m & (pts == k)].mean()*100:+.2f}%" if len(x) else f"{nm} {k}pt n=0")
    print(" | ".join(line))
    m = keep & te; print("    test: P(mean of 2-3pt > mean of 0pt) by bootstrap =", round(boot(r[m & (pts >= 2)], r[m & (pts == 0)]), 3), "| 2-3pt vs 0-1pt:", round(boot(r[m & (pts >= 2)], r[m & (pts <= 1)]), 3))
import pickle; pickle.dump(dict(pts=pts, keep={k: v[0] for k, v in R.items()}), open("conf_pts.pkl", "wb"))
