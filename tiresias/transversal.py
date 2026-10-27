# -*- coding: utf-8 -*-
"""La prueba del S&P 500 (docs/PLAN.md): ¿ordena Kronos los valores ENTRE SÍ?

Cada 5 sesiones (calendario del SPY) desde el 2024-07-01, la rentabilidad prevista a 5 sesiones de cada miembro actual
del índice. Se mide la RankIC entre valores de cada fecha, y la cartera de los 50 primeros frente a la de todos, de
apertura a apertura (como se operaría), con dividendos y un 0,10 % por lo que se rota.

    python -m tiresias.transversal exportar --simbolos-de <descarga.json> --dia 2026-10-28 --fin 2026-10-23 --salida <dir>
    python -m tiresias.transversal predecir --dir <dir> --dispositivo cuda --lote 60      (en la RTX; se puede reanudar)
    python -m tiresias.transversal evaluar --dir <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import platform
import subprocess
import time

import numpy as np
import pandas as pd

from tiresias import evaluar as E
from tiresias import metricas as X

H, PASO, TOP, COSTE = 5, 5, 50, 0.001
CALENDARIO = "SPY"
REPO = pathlib.Path(__file__).resolve().parent.parent


def leer_velas(d: pathlib.Path, s: str) -> pd.DataFrame:
    return pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")


def rejilla(cal: pd.DatetimeIndex, desde: str = E.DESDE, paso: int = PASO) -> list:
    """Fechas de decisión: cada `paso` sesiones desde `desde`, mientras exista la apertura de salida (t + 1 + paso)."""
    i0 = int(cal.searchsorted(pd.Timestamp(desde)))
    return [cal[i] for i in range(i0, len(cal) - 1 - paso, paso)]


# ── matrices fecha × valor ───────────────────────────────────────────────
def matrices(d: pathlib.Path, simbolos: list) -> tuple:
    """(fechas, simbolos, P, Rc, Ro): P la rentabilidad prevista, Rc la real de cierre a cierre (la que predice Kronos)
    y Ro la de apertura a apertura con dividendos, de t+1 a t+1+PASO (la que se cobraría). NaN donde falte."""
    cal = leer_velas(d, CALENDARIO).index
    fechas = rejilla(cal)
    pos = {f: int(cal.get_loc(f)) for f in fechas}      # type: ignore[arg-type]
    P = np.full((len(fechas), len(simbolos)), np.nan)
    Rc, Ro = P.copy(), P.copy()
    for j, s in enumerate(simbolos):
        p = pd.read_csv(d / f"pred_{s}_H{H}.csv", float_precision="round_trip")
        p.index = pd.to_datetime(p["fecha"])
        v = leer_velas(d, s)
        ap = v["open"] * v["adjclose"] / v["close"]
        for i, f in enumerate(fechas):
            if f in p.index:
                P[i, j], Rc[i, j] = p.at[f, "r_prevista"], p.at[f, "r_real"]
            ent, sal = cal[pos[f] + 1], cal[pos[f] + 1 + PASO]
            if ent in ap.index and sal in ap.index:
                Ro[i, j] = ap[sal] / ap[ent] - 1.0
    return fechas, simbolos, P, Rc, Ro


def rankic_por_fecha(P: np.ndarray, R: np.ndarray, minimo: int = 100) -> np.ndarray:
    out = np.full(len(P), np.nan)
    for i in range(len(P)):
        ok = ~np.isnan(P[i]) & ~np.isnan(R[i])
        if ok.sum() >= minimo:
            out[i] = X.spearman(P[i, ok], R[i, ok])
    return out


def cartera(P: np.ndarray, Ro: np.ndarray, top: int | None, coste: float = COSTE) -> np.ndarray:
    """Rentabilidad neta de cada periodo: los `top` mejores según P (None: todos) a partes iguales. El coste, sobre lo
    que se rota: |peso nuevo − peso que dejó el periodo anterior|, sumado (comprarlo todo el primero cuesta 1 × coste)."""
    T, K = P.shape
    w_ant = np.zeros(K)
    out = np.full(T, np.nan)
    for i in range(T):
        ok = ~np.isnan(P[i]) & ~np.isnan(Ro[i])
        idx = np.flatnonzero(ok)
        if top is not None:
            idx = idx[np.argsort(-P[i, idx], kind="stable")[:top]]
        w = np.zeros(K)
        w[idx] = 1.0 / len(idx)
        bruto = float(np.dot(w[idx], Ro[i, idx]))
        out[i] = bruto - coste * float(np.abs(w - w_ant).sum())
        w_ant = np.where(ok, w * (1 + np.nan_to_num(Ro[i])), 0.0) / (1.0 + bruto)
    return out


def barajar_por_valor(P: np.ndarray, rng) -> np.ndarray:
    """El placebo del plan: las predicciones de cada valor, barajadas entre sus fechas."""
    Q = P.copy()
    for j in range(P.shape[1]):
        ok = np.flatnonzero(~np.isnan(P[:, j]))
        Q[ok, j] = P[rng.permutation(ok), j]
    return Q


def sharpe52(r: np.ndarray) -> float:
    return X.sharpe(r[~np.isnan(r)])


def t_media(ic: np.ndarray) -> float:
    """La t de la media de las RankIC semanales. Sin dispersión (todas iguales) es ±∞, no NaN: una señal perfecta y
    constante no puede suspender por eso."""
    v = ic[~np.isnan(ic)]
    if len(v) < 3:
        return float("nan")
    sd = float(v.std(ddof=1))
    if sd == 0:
        return math.copysign(math.inf, v.mean()) if v.mean() != 0 else float("nan")
    return float(v.mean() / (sd / math.sqrt(len(v))))


def condiciones(ic: np.ndarray, sh_top: float, sh_todos: float, p_mejor: float, p95: float) -> dict:
    v = ic[~np.isnan(ic)]
    t = t_media(ic)
    return {"1 RankIC entre valores media > 0 con t > 2": bool(v.mean() > 0 and t > 2),
            "2 los 50 primeros, mejor Sharpe neto que todos con P ≥ 90 %": bool(sh_top > sh_todos and p_mejor >= 0.9),
            "3 por encima del percentil 95 del placebo": bool(sh_top > p95)}


def evaluar(d: pathlib.Path, simbolos: list, placebos: int = 1000, reps: int = 2000) -> dict:
    simbolos = [s for s in simbolos if s != CALENDARIO]    # el SPY es el calendario, no un miembro
    fechas, simbolos, P, Rc, Ro = matrices(d, simbolos)
    ic = rankic_por_fecha(P, Rc)
    ic_ro = rankic_por_fecha(P, Ro)
    top, todos = cartera(P, Ro, TOP), cartera(P, Ro, None)
    idx = pd.DatetimeIndex(fechas)
    p_m = X.p_mejor(pd.Series(top, index=idx), pd.Series(todos, index=idx), reps)
    rng = np.random.default_rng(20261028)
    plac = np.array([sharpe52(cartera(barajar_por_valor(P, rng), Ro, TOP)) for _ in range(placebos)])
    azar = np.array([sharpe52(cartera(np.where(np.isnan(P), np.nan, rng.random(P.shape)), Ro, TOP)) for _ in range(200)])
    ultimos = cartera(-P, Ro, TOP)                      # exploratorio: si ordena, los últimos van peor que los primeros
    p95 = float(np.nanpercentile(plac, 95))
    v = ic[~np.isnan(ic)]
    cond = condiciones(ic, sharpe52(top), sharpe52(todos), p_m, p95)
    años = len(top) * PASO / 252
    return {"fechas": len(fechas), "valores_con_prediccion": int((~np.isnan(P)).any(axis=0).sum()),
            "valores_por_fecha_mediana": float(np.median((~np.isnan(P)).sum(axis=1))),
            "rankic_media": float(v.mean()), "rankic_t": t_media(ic),
            "rankic_positivas": float((v > 0).mean()), "rankic_media_apertura": float(np.nanmean(ic_ro)),
            "sharpe_top": sharpe52(top), "sharpe_todos": sharpe52(todos),
            "cagr_top": float(np.prod(1 + top) ** (1 / años) - 1), "cagr_todos": float(np.prod(1 + todos) ** (1 / años) - 1),
            "p_mejor": p_m, "placebo_p50": float(np.nanmedian(plac)), "placebo_p95": p95, "placebo_sharpes": plac.tolist(),
            "azar_p50": float(np.nanmedian(azar)), "azar_p95": float(np.nanpercentile(azar, 95)),
            "sharpe_ultimos": sharpe52(ultimos), "cagr_ultimos": float(np.prod(1 + ultimos) ** (1 / años) - 1),
            "condiciones": cond, "aporta": all(cond.values()),
            "ic_por_fecha": dict(zip([str(f.date()) for f in fechas], [None if np.isnan(x) else float(x) for x in ic]))}


# ── CLI ──────────────────────────────────────────────────────────────────
def _exportar(a) -> int:
    from tiresias import datos as D
    info = json.loads(pathlib.Path(a.simbolos_de).read_text(encoding="utf-8"))
    sal = pathlib.Path(a.salida).expanduser()
    sal.mkdir(parents=True, exist_ok=True)
    buenos = [s for s in info["simbolos"] if s not in info["fallos"] and s != CALENDARIO]
    for s in [CALENDARIO] + buenos:                         # el SPY va como calendario, no como miembro
        D.velas(s, a.fin, a.dia).to_csv(sal / f"velas_{s}.csv")
    (sal / "simbolos.json").write_text(json.dumps({"simbolos": buenos, "fin": a.fin, "dia": a.dia,
                                                   "excluidos": info["fallos"]}, indent=1), encoding="utf-8")
    print(f"{len(buenos)} valores exportados ({len(info['fallos'])} excluidos: {sorted(info['fallos'])})")
    return 0


def _predecir(a) -> int:
    import torch

    from tiresias import modelo as M
    d = pathlib.Path(a.dir).expanduser()
    info = json.loads((d / "simbolos.json").read_text(encoding="utf-8"))
    fechas = rejilla(leer_velas(d, CALENDARIO).index)
    tok, mod = M.cargar(a.modelo, a.dispositivo)
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    pro = {"commit": commit, "dispositivo": a.dispositivo, "torch": torch.__version__.split("+")[0], "modelo": a.modelo,
           "gpu": torch.cuda.get_device_name(0) if a.dispositivo.startswith("cuda") else None, "sistema": platform.system(),
           "N": a.N, "lote": a.lote, "H": H, "paso": PASO, "desde": E.DESDE, "fin": info["fin"], "dia_descarga": info["dia"],
           "fechas": len(fechas), "inicio": time.strftime("%Y-%m-%dT%H:%M:%S")}
    hechos = 0
    for k, s in enumerate(info["simbolos"], 1):
        f = d / f"pred_{s}_H{H}.csv"
        if f.exists():
            continue
        t0 = time.time()
        p = E.predecir(tok, mod, leer_velas(d, s), s, H, N=a.N, lote=a.lote, solo=fechas)
        p.to_csv(f.with_suffix(".tmp"), index=False)
        f.with_suffix(".tmp").replace(f)                    # atómico: un corte no deja un fichero a medias
        hechos += 1
        print(f"{k}/{len(info['simbolos'])} {s}: {len(p)} fechas en {time.time() - t0:.1f} s", flush=True)
    pro["fin_ejecucion"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    pro["hechos_en_esta_pasada"] = hechos
    (d / "procedencia.json").write_text(json.dumps(pro, indent=1), encoding="utf-8")
    return 0


def _evaluar(a) -> int:
    d = pathlib.Path(a.dir).expanduser()
    info = json.loads((d / "simbolos.json").read_text(encoding="utf-8"))
    faltan = [s for s in info["simbolos"] if not (d / f"pred_{s}_H{H}.csv").exists()]
    if faltan:
        raise SystemExit(f"⛔ faltan predicciones de {len(faltan)} valores: {faltan[:10]}")
    r = evaluar(d, info["simbolos"], a.placebos)
    r["procedencia"] = json.loads((d / "procedencia.json").read_text(encoding="utf-8"))
    (d / "veredicto_sp500.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'APORTA' if r['aporta'] else 'NO APORTA'} · {r['fechas']} fechas, ~{r['valores_por_fecha_mediana']:.0f} valores por fecha")
    print(f"   RankIC entre valores: media {r['rankic_media']:+.4f}, t {r['rankic_t']:+.2f}, positiva {r['rankic_positivas']:.0%} "
          f"de las semanas (de apertura a apertura: {r['rankic_media_apertura']:+.4f})")
    print(f"   los 50 primeros: Sharpe {r['sharpe_top']:.2f}, CAGR {r['cagr_top']:+.1%} · todos: Sharpe {r['sharpe_todos']:.2f}, "
          f"CAGR {r['cagr_todos']:+.1%} · P(mejor) {r['p_mejor']:.2f}")
    print(f"   exploratorio, los 50 últimos: Sharpe {r['sharpe_ultimos']:.2f}, CAGR {r['cagr_ultimos']:+.1%}")
    print(f"   placebo del plan p50 {r['placebo_p50']:.2f} p95 {r['placebo_p95']:.2f} · 50 al azar p50 {r['azar_p50']:.2f} p95 {r['azar_p95']:.2f}")
    for k, v in r["condiciones"].items():
        print(f"   {'sí' if v else 'NO'} · {k}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("exportar")
    e.add_argument("--simbolos-de", required=True)
    e.add_argument("--fin", required=True)
    e.add_argument("--dia", required=True)
    e.add_argument("--salida", required=True)
    p = sub.add_parser("predecir")
    p.add_argument("--dir", required=True)
    p.add_argument("--dispositivo", default="cuda")
    p.add_argument("--modelo", default="small")
    p.add_argument("--N", type=int, default=10)
    p.add_argument("--lote", type=int, default=60)
    v = sub.add_parser("evaluar")
    v.add_argument("--dir", required=True)
    v.add_argument("--placebos", type=int, default=1000)
    a = ap.parse_args(argv)
    return {"exportar": _exportar, "predecir": _predecir, "evaluar": _evaluar}[a.orden](a)


if __name__ == "__main__":
    raise SystemExit(main())
