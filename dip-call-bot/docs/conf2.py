import numpy as np, pandas as pd, pickle, warnings
warnings.filterwarnings("ignore")
exec(open("conf.py").read().split('rng = np.random.default_rng(1)')[0])
pts = (F.dd.values < -0.05).astype(int) + (F.vix.values > 22) + (F.nfire.values >= 2)
yr = u.dates.year.values
for rid in ["S1", "K2", "K1"]:
    keep, r, und = R[rid]; m = keep & te; hi = m & (pts >= 2); lo = m & (pts <= 1)
    print(f"\n{rid} test 2014-2026: high (2-3 pts) n={hi.sum()} mean={r[hi].mean()*100:+.0f}% median={np.median(r[hi])*100:+.0f}% win={(r[hi]>0).mean()*100:.0f}% | low (0-1) n={lo.sum()} mean={r[lo].mean()*100:+.0f}% median={np.median(r[lo])*100:+.0f}% win={(r[lo]>0).mean()*100:.0f}%")
    rows = []
    for y in sorted(set(yr[m])):
        a, b = hi & (yr == y), lo & (yr == y)
        rows.append((y, a.sum(), r[a].mean()*100 if a.sum() else np.nan, b.sum(), r[b].mean()*100 if b.sum() else np.nan))
    t = pd.DataFrame(rows, columns=["yr", "n_hi", "mean_hi", "n_lo", "mean_lo"]); print(t.round(0).to_string(index=False))
    both = t[(t.n_hi >= 3) & (t.n_lo >= 3)]; print("years with >=3 trades in both groups where high beat low:", int((both.mean_hi > both.mean_lo).sum()), "of", len(both))
    # leave-one-year-out and drop top 5 trades
    worst = min(((r[hi & (yr != y)].mean() - r[lo & (yr != y)].mean()), y) for y in set(yr[m]))
    x = np.sort(r[hi])[:-5]; print(f"smallest high-minus-low gap after dropping any one year: {worst[0]*100:+.0f} pts (dropping {worst[1]}); high-group mean without its 5 best trades: {x.mean()*100:+.0f}%")
    # share of high-group profit from top 10% of trades
    s = np.sort(r[hi])[::-1]; k = max(1, len(s)//10); print(f"top 10% of high-group trades supply {s[:k].sum()/s.sum()*100:.0f}% of its total return; worst run of consecutive losers in high group: {max(len(g) for g in ''.join('L' if v<=0 else 'W' for v in r[hi]).split('W'))}")
    # stress pricing: high-vol options 15% dearer at entry for the high group only (model error where it matters)
    p, v, K = u.multi_struct("C", dict(S1=.07, K2=.30, K1=.15)[rid], dict(S1=5, K2=10, K1=5)[rid], 2, entry_iv_mult=1.15); r2 = net(p, v, u.cm)
    print(f"if entry implied vol were 15% higher than modelled: high-group mean {r2[hi].mean()*100:+.0f}%, low-group {r2[lo].mean()*100:+.0f}%")
# full-sample calibration table for the bot (tiers), and today's reading
print("\nFull 2001-2026 calibration by points (mean, win, n):")
for rid in R:
    keep, r, und = R[rid]; m = keep & era
    print(rid, " | ".join(f"{k}pt n={int((m&(pts==k)).sum())} mean={r[m&(pts==k)].mean()*100:+.0f}% win={(r[m&(pts==k)]>0).mean()*100:.0f}%" if (m&(pts==k)).sum() else f"{k}pt n=0" for k in range(4)))
print("share of S1 signal days by points, 2014-2026:", {k: round(float(((pts==k)&R['S1'][0]&te).sum()/(R['S1'][0]&te).sum()),2) for k in range(4)})
print("last row:", u.dates[-1].date(), "dd", round(F.dd.values[-1],4), "vix", F.vix.values[-1], "nfire", F.nfire.values[-1], "52w high", round(hi_ := float((d.close.rolling(252,min_periods=120).max()).iloc[-1]),2))
