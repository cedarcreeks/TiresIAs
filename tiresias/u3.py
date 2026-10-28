# -*- coding: utf-8 -*-
"""U3 (docs/PLAN_UTILIDAD.md): una cabeza sencilla sobre la representación interna de Kronos.

El estado interno es el contexto de `decode_s1` (tras la última capa y su normalización) en la última vela de cada
ventana de 40, preparada como en la predicción: el mismo camino que usa Kronos para generar, sin muestrear. La vara son
ocho características clásicas. Ridge sobre el puesto de la rentabilidad a 5 sesiones, con el alfa elegido en bloques
dentro del desarrollo (2024-07 → 2025-06); prueba única en 2025-07 → 2026-10.

    python -m tiresias.u3 estados --dir ~/tiresias_resultados/sp500/datos --salida ~/tiresias_resultados/ronda2/u3
    python -m tiresias.u3 evaluar --dir ~/tiresias_resultados/sp500/datos --estados ~/tiresias_resultados/ronda2/u3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np
import pandas as pd
import torch

from tiresias import evaluar as E
from tiresias import metricas as X
from tiresias import modelo as M
from tiresias import ronda2 as R2
from tiresias import transversal as T
from model.kronos import calc_time_stamps

CORTE = "2025-07-01"
ALFAS = [1.0, 10.0, 100.0, 1000.0, 10000.0]
CLASICAS = ["r1", "r5", "r20", "r60", "vol20", "park20", "volu5_60", "dist_max252"]


# ── estados internos ─────────────────────────────────────────────────────
@torch.no_grad()
def estados(tok, mod, df: pd.DataFrame, posiciones: list, lote: int = 256) -> np.ndarray:
    """[posiciones × d_model]: el contexto en la última vela de la ventana de L velas que acaba en cada posición."""
    disp = next(mod.parameters()).device
    out = []
    for k in range(0, len(posiciones), lote):
        trozo = posiciones[k:k + lote]
        xs, st = [], []
        for i in trozo:
            w = M._preparar(df.iloc[i - E.L + 1:i + 1][E.ENTRADA].reset_index(drop=True))[M.COLUMNAS].to_numpy(np.float32)
            xs.append(np.clip((w - w.mean(axis=0)) / (w.std(axis=0) + 1e-5), -5, 5))
            st.append(calc_time_stamps(pd.Series(df.index[i - E.L + 1:i + 1])).to_numpy(np.float32))
        x = torch.from_numpy(np.stack(xs)).to(disp)
        s = torch.from_numpy(np.stack(st)).to(disp)
        s0, s1 = tok.encode(x, half=True)
        _, ctx = mod.decode_s1(s0, s1, s)
        out.append(ctx[:, -1, :].float().cpu().numpy())
    return np.concatenate(out)


def _posiciones(df: pd.DataFrame, fechas: pd.DatetimeIndex) -> tuple:
    i = df.index.get_indexer(fechas)
    ok = (i >= E.L - 1)
    return [int(x) for x in i[ok]], fechas[ok]


# ── características clásicas, sólo con el pasado ─────────────────────────
def clasicas(v: pd.DataFrame) -> pd.DataFrame:
    c, lr = v["close"], np.log(v["close"]).diff()
    return pd.DataFrame({
        "r1": c.pct_change(1), "r5": c.pct_change(5), "r20": c.pct_change(20), "r60": c.pct_change(60),
        "vol20": lr.rolling(20).std(), "park20": R2_parkinson(v),
        "volu5_60": v["volume"].rolling(5).mean() / v["volume"].rolling(60).mean(),
        "dist_max252": c / c.rolling(252).max() - 1.0}, index=v.index)


def R2_parkinson(v: pd.DataFrame, n: int = 20) -> pd.Series:
    return np.sqrt((np.log(v["high"] / v["low"]) ** 2).rolling(n).mean() / (4 * np.log(2)))


# ── la cabeza ────────────────────────────────────────────────────────────
def _por_fecha(Z: np.ndarray, fechas: np.ndarray, rangos: bool) -> np.ndarray:
    """Cada columna, normalizada dentro de cada fecha (rangos centrados, o z): sólo cuenta el orden entre valores."""
    out = np.empty_like(Z, dtype=float)
    for f in np.unique(fechas):
        m = fechas == f
        bloque = pd.DataFrame(Z[m])
        if rangos:
            out[m] = (bloque.rank().to_numpy() - 0.5) / m.sum() - 0.5
        else:
            out[m] = ((bloque - bloque.mean()) / (bloque.std(ddof=0) + 1e-12)).to_numpy()
    return np.nan_to_num(out)


def ridge(Xm: np.ndarray, y: np.ndarray, alfa: float) -> np.ndarray:
    A = Xm.T @ Xm + alfa * np.eye(Xm.shape[1])
    return np.linalg.solve(A, Xm.T @ y)


def ic_medio(pred: np.ndarray, y: np.ndarray, fechas: np.ndarray) -> float:
    return float(np.nanmean([X.spearman(pred[fechas == f], y[fechas == f]) for f in np.unique(fechas)]))


def elegir_alfa(Xm: np.ndarray, y: np.ndarray, fechas: np.ndarray, bloques: int = 4) -> float:
    """Validación en bloques de fechas contiguas, todo dentro del desarrollo: el alfa con mejor RankIC media fuera del bloque."""
    orden = np.unique(fechas)
    cortes = np.array_split(orden, bloques)
    mejor, alfa_m = -np.inf, ALFAS[0]
    for a in ALFAS:
        ics = []
        for b in cortes:
            prueba = np.isin(fechas, b)
            w = ridge(Xm[~prueba], y[~prueba], a)
            ics.append(ic_medio(Xm[prueba] @ w, y[prueba], fechas[prueba]))
        if np.mean(ics) > mejor:
            mejor, alfa_m = float(np.mean(ics)), a
    return alfa_m


# ── CLI ──────────────────────────────────────────────────────────────────
def _estados_cli(a) -> int:
    d, sal = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.salida).expanduser()
    sal.mkdir(parents=True, exist_ok=True)
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    cal = T.leer_velas(d, T.CALENDARIO).index
    fechas = cal[(cal >= pd.Timestamp(E.DESDE)) & (cal <= cal[-6])]          # con la rentabilidad a 5 sesiones conocida
    tok, mod = M.cargar("small", a.dispositivo)
    for k, s in enumerate(simbolos, 1):
        f = sal / f"estados_{s}.npz"
        if f.exists():
            continue
        t0 = time.time()
        v = T.leer_velas(d, s)
        pos, fs = _posiciones(v, fechas)
        np.savez(f, estados=estados(tok, mod, v, pos), fechas=np.array([str(x.date()) for x in fs]))
        print(f"{k}/{len(simbolos)} {s}: {len(pos)} fechas en {time.time() - t0:.1f} s", flush=True)
    return 0


def _evaluar_cli(a) -> int:
    d, de = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.estados).expanduser()
    r = evaluar(d, de)
    (de / "u3.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(f"U3 · prueba: RankIC Kronos+clásicas {r['ic_comb']:+.4f} · sólo clásicas {r['ic_clas']:+.4f} · diferencia "
          f"{r['dif_media']:+.4f}, t {r['dif_t']:+.2f}, p {r['p']:.3f} ({r['semanas']} semanas) · alfas {r['alfa_comb']:g}/"
          f"{r['alfa_clas']:g} · los 50 primeros: Sharpe {r['sharpe_top']:.2f} frente a {r['sharpe_todos']:.2f}, "
          f"P(mejor) {r['p_mejor']:.2f}")
    return 0


def tabla(d: pathlib.Path, de: pathlib.Path) -> pd.DataFrame:
    """Una fila por (valor, fecha): estados, clásicas y el real a 5 sesiones de cierre a cierre."""
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    filas = []
    for s in simbolos:
        z = np.load(de / f"estados_{s}.npz")
        v = T.leer_velas(d, s)
        cl = clasicas(v)
        real = v["close"].shift(-5) / v["close"] - 1.0
        f = pd.to_datetime(z["fechas"])
        bloque = pd.DataFrame(z["estados"], index=f).add_prefix("k")
        bloque = bloque.join(cl.reindex(f)).assign(real=real.reindex(f).to_numpy(), simbolo=s)
        filas.append(bloque)
    return pd.concat(filas).rename_axis("fecha").reset_index()


def evaluar(d: pathlib.Path, de: pathlib.Path) -> dict:
    t = tabla(d, de).dropna(subset=CLASICAS + ["real"])
    kcols = [c for c in t.columns if c.startswith("k")]
    fechas = t["fecha"].to_numpy()
    y = _por_fecha(t[["real"]].to_numpy(), fechas, True)[:, 0]
    Xc = _por_fecha(t[CLASICAS].to_numpy(), fechas, True)
    Xk = _por_fecha(t[kcols].to_numpy(), fechas, False)
    Xb = np.column_stack([Xc, Xk])
    dev = t["fecha"] < pd.Timestamp(CORTE)
    out = {}
    for nombre, Xm in (("clas", Xc), ("comb", Xb)):
        alfa = elegir_alfa(Xm[dev.to_numpy()], y[dev.to_numpy()], fechas[dev.to_numpy()])
        w = ridge(Xm[dev.to_numpy()], y[dev.to_numpy()], alfa)
        out[nombre] = (alfa, Xm @ w)
    # la prueba, una vez: en las fechas de la rejilla semanal de la primera ronda que caen en 2025-07 →
    rej = [f for f in T.rejilla(T.leer_velas(d, T.CALENDARIO).index) if f >= pd.Timestamp(CORTE)]
    ics = {n: [] for n in out}
    for f in rej:
        m = fechas == np.datetime64(f)
        if m.sum() < 100:
            continue
        for n in out:
            ics[n].append(X.spearman(out[n][1][m], t["real"].to_numpy()[m]))
    dif = np.array(ics["comb"]) - np.array(ics["clas"])
    rt = R2.resumen_t(dif)
    # la cartera: los 50 primeros de la cabeza combinada, cada semana, de apertura a apertura y neta
    simbolos = sorted(t["simbolo"].unique())
    fechas_g, simbolos, _, _, Ro = T.matrices(d, simbolos)
    P = np.full(Ro.shape, np.nan)
    idx = {s: j for j, s in enumerate(simbolos)}
    pos_f = {f: i for i, f in enumerate(fechas_g)}
    for (f, s), val in zip(zip(t["fecha"], t["simbolo"]), out["comb"][1]):
        if f in pos_f and f >= pd.Timestamp(CORTE):
            P[pos_f[f], idx[s]] = val
    filas = [i for i, f in enumerate(fechas_g) if f >= pd.Timestamp(CORTE)]
    top, todos = T.cartera(P[filas], Ro[filas], T.TOP), T.cartera(P[filas], Ro[filas], None)
    ix = pd.DatetimeIndex([fechas_g[i] for i in filas])
    return {"ic_comb": float(np.mean(ics["comb"])), "ic_clas": float(np.mean(ics["clas"])), "semanas": rt["n"],
            "dif_media": rt["media"], "dif_t": rt["t"], "p": rt["p"], "alfa_comb": out["comb"][0], "alfa_clas": out["clas"][0],
            "sharpe_top": T.sharpe52(top), "sharpe_todos": T.sharpe52(todos),
            "p_mejor": X.p_mejor(pd.Series(top, index=ix), pd.Series(todos, index=ix))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("estados")
    e.add_argument("--dir", required=True)
    e.add_argument("--salida", required=True)
    e.add_argument("--dispositivo", default="cpu")
    v = sub.add_parser("evaluar")
    v.add_argument("--dir", required=True)
    v.add_argument("--estados", required=True)
    a = ap.parse_args(argv)
    return {"estados": _estados_cli, "evaluar": _evaluar_cli}[a.orden](a)


if __name__ == "__main__":
    raise SystemExit(main())
