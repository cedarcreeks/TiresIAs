# -*- coding: utf-8 -*-
"""EXPLORATORIO (28-oct): minería de reglas sobre las salidas de Kronos (probabilidad de subida y anchura del abanico).
91 reglas por valor elegidas en 2024-07 → 2025-06 por Sharpe, probadas UNA vez en 2025-07 → 2026-10, contra 200 placebos
(el mismo procedimiento con las salidas barajadas). Criterio, escrito antes: ganar a mantener y al p95 del placebo. No aprueba.

    PYTHONPATH=. python exploratorio/mineria_reglas.py   (con ~/tiresias_resultados/cinco de tiresias.correr)
"""
import pathlib, numpy as np, pandas as pd
from tiresias import metricas as X, informe as I
d = pathlib.Path.home() / "tiresias_resultados/cinco"
S, CORTE = ["IDR.MC", "ACS.MC", "SPY", "3USL.MI", "BTC-EUR"], pd.Timestamp("2025-07-01")
A, Q = np.round(np.arange(0.1, 1.0, 0.1), 1), [0.2, 0.4, 0.6, 0.8, 1.0]

def sharpe5(c):                      # sólo para ordenar reglas dentro de un valor
    v = c.to_numpy()[::5]; r = v[1:] / v[:-1] - 1
    return r.mean() / r.std(ddof=1) if len(r) > 2 and r.std(ddof=1) > 0 else -np.inf

datos = {}
for s in S:
    v = pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
    p = pd.read_csv(d / f"pred_{s}_H5.csv", float_precision="round_trip").sort_values("fecha").iloc[::5].reset_index(drop=True)
    p["f"] = pd.to_datetime(p.fecha); p["abanico"] = p.r_p90 - p.r_p10
    coste = I.COSTES.get(s, I.COSTE_ACCIONES)
    dev, tst = p[p.f < CORTE].reset_index(drop=True), p[p.f >= CORTE].reset_index(drop=True)
    datos[s] = (dev, tst, X.Simulador(v, dev.f, 5, coste), X.Simulador(v, tst.f, 5, coste))

def cdev(sim, x):
    """La curva de desarrollo acaba donde acaba su última decisión: sin la cola plana hasta 2026 (ceros en el Sharpe)."""
    c = sim.curva(x)
    fin = min(int(sim.i[-1]) + 1 + sim.paso, len(sim.fechas) - 1)
    return c.loc[:sim.fechas[fin]]

def reglas(ps, ab, cortes_ab):
    yield "siempre", np.ones(len(ps), bool)
    for a in A:
        for q, cab in zip(Q, cortes_ab):
            yield f">={a} ab<=q{q}", (ps >= a) & (ab <= cab)
            yield f"<={a} ab<=q{q}", (ps <= a) & (ab <= cab)

def minar(rng=None):
    curvas, elegidas = {}, {}
    for s in S:
        dev, tst, sd, st = datos[s]
        pd_, ad, pt, at = dev.p_subida.to_numpy(), dev.abanico.to_numpy(), tst.p_subida.to_numpy(), tst.abanico.to_numpy()
        if rng is not None:                      # placebo: las salidas barajadas entre fechas, en cada periodo
            i, j = rng.permutation(len(pd_)), rng.permutation(len(pt)); pd_, ad, pt, at = pd_[i], ad[i], pt[j], at[j]
        cortes = [np.quantile(ad, q) for q in Q]  # cuantiles SÓLO del desarrollo
        mejor = max(reglas(pd_, ad, cortes), key=lambda r: sharpe5(cdev(sd, r[1])))
        nombre = mejor[0]
        regla_t = dict(reglas(pt, at, cortes))[nombre]
        curvas[s], elegidas[s] = st.curva(regla_t), (nombre, sharpe5(cdev(sd, mejor[1])))
    return X.sharpe(X.semanales(X.cartera(curvas))), elegidas, curvas

sh, eleg, curv = minar()
bh = X.sharpe(X.semanales(X.cartera({s: datos[s][3].curva(np.ones(len(datos[s][1]))) for s in S})))
rng = np.random.default_rng(20261028)
plac = np.array([minar(rng)[0] for _ in range(200)])
print("reglas elegidas en desarrollo:"); [print(f"   {s:8} {n:18} (Sharpe por 5 sesiones en desarrollo {v:+.3f})") for s, (n, v) in eleg.items()]
print(f"\nPRUEBA 2025-07 → 2026-10 (una vez): Sharpe cartera reglas {sh:.2f} · mantener {bh:.2f} · placebo p50 {np.median(plac):.2f} p95 {np.percentile(plac, 95):.2f}")
print(f"   P(placebo ≥ reglas) = {(plac >= sh).mean():.2f}")
print("   APRUEBA" if (sh > bh and sh > np.percentile(plac, 95)) else "   NO APRUEBA")

# el otro lado: cómo lucían en DESARROLLO (donde se eligieron), las de Kronos y las del ruido
def en_desarrollo(rng=None):
    curvas = {}
    for s in S:
        dev, _, sd, _ = datos[s]
        pd_, ad = dev.p_subida.to_numpy(), dev.abanico.to_numpy()
        if rng is not None:
            i = rng.permutation(len(pd_)); pd_, ad = pd_[i], ad[i]
        cortes = [np.quantile(ad, q) for q in Q]
        mejor = max(reglas(pd_, ad, cortes), key=lambda r: sharpe5(cdev(sd, r[1])))
        curvas[s] = cdev(sd, mejor[1])
    return X.sharpe(X.semanales(X.cartera(curvas)))
bh_dev = X.sharpe(X.semanales(X.cartera({s: cdev(datos[s][2], np.ones(len(datos[s][0]))) for s in S})))
r2 = np.random.default_rng(7)
pd_dev = np.array([en_desarrollo(r2) for _ in range(200)])
print(f"\nDESARROLLO 2024-07 → 2025-06 (donde se eligieron): Sharpe cartera reglas {en_desarrollo():.2f} · mantener {bh_dev:.2f} · "
      f"reglas del ruido barajado p50 {np.median(pd_dev):.2f} p95 {np.percentile(pd_dev, 95):.2f}")
