# -*- coding: utf-8 -*-
"""Segunda ronda (docs/PLAN_UTILIDAD.md): las hipótesis U1–U5, cada una con su p principal y su criterio económico.

    python -m tiresias.ronda2 u2 --sp500 ~/tiresias_resultados/sp500/datos
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np
import pandas as pd

from tiresias import estadistica as ES
from tiresias import metricas as X
from tiresias import transversal as T


def pasados(dsp: pathlib.Path, simbolos: list, fechas: list, n: int) -> np.ndarray:
    """[fechas × valores]: la rentabilidad de cierre a cierre de las `n` sesiones anteriores (hasta la fecha incluida)."""
    cal = T.leer_velas(dsp, T.CALENDARIO).index
    out = np.full((len(fechas), len(simbolos)), np.nan)
    for j, s in enumerate(simbolos):
        c = T.leer_velas(dsp, s)["close"]
        for i, f in enumerate(fechas):
            antes = cal[int(cal.get_loc(f)) - n]                    # type: ignore[arg-type]
            if f in c.index and antes in c.index:
                out[i, j] = c[f] / c[antes] - 1.0
    return out


def _rango(x: np.ndarray) -> np.ndarray:
    return (pd.Series(x).rank().to_numpy() - 0.5) / len(x) - 0.5


def residuo_ic(P: np.ndarray, R: np.ndarray, controles: list, minimo: int = 100) -> np.ndarray:
    """RankIC por fecha del residuo de P (en rangos) tras regresarlo, en esa fecha, sobre los controles (en rangos)."""
    out = np.full(len(P), np.nan)
    for i in range(len(P)):
        ok = ~np.isnan(P[i]) & ~np.isnan(R[i])
        for c in controles:
            ok &= ~np.isnan(c[i])
        if ok.sum() < minimo:
            continue
        y = _rango(P[i, ok])
        Xm = np.column_stack([np.ones(ok.sum())] + [_rango(c[i, ok]) for c in controles])
        res = y - Xm @ np.linalg.lstsq(Xm, y, rcond=None)[0]
        if np.std(res) > 1e-12:
            out[i] = X.spearman(res, R[i, ok])
    return out


def resumen_t(ic: np.ndarray) -> dict:
    v = ic[~np.isnan(ic)]
    t = T.t_media(ic)
    p = ES.p_t(t, len(v) - 1) if len(v) > 2 and math.isfinite(t) else (0.0 if t == math.inf else float("nan"))
    return {"n": len(v), "media": float(v.mean()) if len(v) else float("nan"), "t": t, "p": p}


def u2(dsp: pathlib.Path) -> dict:
    simbolos = [s for s in json.loads((dsp / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    fechas, simbolos, P, Rc, _ = T.matrices(dsp, simbolos)
    p5, p20 = pasados(dsp, simbolos, fechas, 5), pasados(dsp, simbolos, fechas, 20)
    r = resumen_t(residuo_ic(P, Rc, [p5, p20]))
    r["sin_descontar"] = resumen_t(T.rankic_por_fecha(P, Rc))
    return r


# ── U5 · bitcoin ─────────────────────────────────────────────────────────
COSTE_BTC = 0.0149


def e006(cierres: pd.Series, sma: int = 200) -> pd.Series:
    """La regla de la incubadora: dentro si el cierre supera su media de 200 (que incluye el de hoy)."""
    return cierres > cierres.rolling(sma).mean()


def con_veto(regla: pd.Series, kronos_sube: pd.Series) -> pd.Series:
    """La regla con el veto de Kronos SÓLO a las entradas: entra el primer día en que la regla está dentro y Kronos da
    más de 0,5 de subida; sale cuando sale la regla. Un día sin opinión de Kronos no deja entrar."""
    k = kronos_sube.reindex(regla.index).fillna(False).astype(bool)
    out, dentro = [], False
    for r, ks in zip(regla.to_numpy(), k.to_numpy()):
        dentro = bool(r) and (dentro or ks)
        out.append(dentro)
    return pd.Series(out, index=regla.index)


def curva_regla(cierres: pd.Series, dentro: pd.Series, coste: float = COSTE_BTC) -> pd.Series:
    """La señal del cierre d decide el día siguiente (como E006 en la incubadora), de cierre a cierre, con coste por cambio."""
    pos = dentro.astype(float).shift(1).fillna(0.0)
    r = cierres.pct_change().fillna(0.0)
    cambio = pos.diff().abs().fillna(pos.abs())
    return (1 + pos * r - coste * cambio).cumprod()


def u5(cinco: pathlib.Path, btc_usd: pathlib.Path, desde: str = "2024-07-01", reps: int = 10000) -> dict:
    p = pd.read_csv(btc_usd, float_precision="round_trip")
    q = X.sin_solape(p, 5)
    ic = X.spearman(q["r_prevista"], q["r_real"])
    rem = X.ic_remuestreado({"BTC-USD": q}, reps, 0)[:, 0]
    eur = pd.read_csv(cinco / "velas_BTC-EUR.csv", index_col=0, parse_dates=True, float_precision="round_trip")["close"]
    regla = e006(eur)
    ks = pd.Series((p["p_subida"] > 0.5).to_numpy(), index=pd.to_datetime(p["fecha"]))
    tramo = regla.loc[desde:]
    sola = curva_regla(eur.loc[desde:], tramo)
    veto = curva_regla(eur.loc[desde:], con_veto(tramo, ks))
    sem_s, sem_v = X.semanales(sola), X.semanales(veto)
    cambios = lambda d: int(d.astype(int).diff().abs().fillna(d.astype(int)).sum())      # noqa: E731
    return {"rankic": ic, "p": float(np.mean(rem <= 0)), "fechas_sin_solape": len(q),
            "sharpe_e006": X.sharpe(sem_s), "sharpe_veto": X.sharpe(sem_v), "p_mejor": X.p_mejor(sem_v, sem_s),
            "cagr_e006": X.cagr(sola), "cagr_veto": X.cagr(veto),
            "operaciones_e006": cambios(tramo), "operaciones_veto": cambios(con_veto(tramo, ks))}


# ── veredicto de la ronda: Holm sobre el p principal de cada una ─────────
def veredicto(r: dict) -> list:
    """Una fila por hipótesis con su p principal, si sobrevive a Holm al 5 % y su criterio económico (None si el plan no
    le pone ninguno: U2 es un diagnóstico). Pasa si sobrevive a Holm Y cumple el económico."""
    principal = {"U1": r["U1"]["principal"]["p"], "U2": r["U2"]["p"], "U3": r["U3"]["p"],
                 "U4": r["U4"]["rankic_10"]["p"], "U5": r["U5"]["p"]}
    economico = {"U1": r["U1"]["principal"]["p_exceso_positivo"] >= 0.9, "U2": None, "U3": r["U3"]["p_mejor"] >= 0.9,
                 "U4": r["U4"]["pasa_economico"], "U5": r["U5"]["p_mejor"] >= 0.9}
    h = ES.holm(principal)
    return [{"hipotesis": k, "p": principal[k], "holm": h[k], "economico": economico[k],
             "pasa": bool(h[k] and economico[k] is not False)} for k in sorted(principal)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    av = sub.add_parser("veredicto")
    for k in ("u1", "u2", "u3", "u4", "u5"):
        av.add_argument(f"--{k}", required=True)
    a2 = sub.add_parser("u2")
    a2.add_argument("--sp500", required=True)
    a2.add_argument("--salida", required=True)
    a5 = sub.add_parser("u5")
    a5.add_argument("--cinco", required=True)
    a5.add_argument("--pred", required=True, help="predicciones de BTC-USD a 5 con su protocolo de cripto")
    a5.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    if a.orden == "veredicto":
        r = {k: json.loads(pathlib.Path(getattr(a, k.lower())).expanduser().read_text(encoding="utf-8"))
             for k in ("U1", "U2", "U3", "U4", "U5")}
        filas = veredicto(r)
        for f in filas:
            eco = "—" if f["economico"] is None else ("sí" if f["economico"] else "no")
            print(f"{f['hipotesis']}: p {f['p']:.3f} · Holm {'sí' if f['holm'] else 'no'} · económico {eco} · "
                  f"{'PASA' if f['pasa'] else 'no pasa'}")
        print(f"pasan {len([f for f in filas if f['pasa']])} de {len(filas)}")
        return 0
    if a.orden == "u5":
        r = u5(pathlib.Path(a.cinco).expanduser(), pathlib.Path(a.pred).expanduser())
        pathlib.Path(a.salida).expanduser().write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"U5 · BTC-USD sin volumen: RankIC {r['rankic']:+.4f} (p {r['p']:.3f}, {r['fechas_sin_solape']} fechas) · "
              f"E006 sola Sharpe {r['sharpe_e006']:.2f} ({r['operaciones_e006']} cambios) · con veto "
              f"{r['sharpe_veto']:.2f} ({r['operaciones_veto']} cambios) · P(mejor) {r['p_mejor']:.2f}")
    if a.orden == "u2":
        r = u2(pathlib.Path(a.sp500).expanduser())
        pathlib.Path(a.salida).expanduser().write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"U2 · residuo tras descontar la última semana y las 20 sesiones: RankIC media {r['media']:+.4f}, "
              f"t {r['t']:+.2f}, p {r['p']:.3f} ({r['n']} semanas) · sin descontar {r['sin_descontar']['media']:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
