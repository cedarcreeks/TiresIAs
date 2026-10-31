"""Fase 3A: ¿persiste el resultado de los traders de Hyperliquid? (docs/PLAN_FASE3.md, apartado 3A).

  1. `muestra`: 6.000 cuentas al azar de la clasificación, con semilla fija (fijada antes de bajar ninguna curva).
  2. `descargar`: la curva de cada cuenta (`portfolio`), reanudable y con espera ante 429.
  3. `rendimiento`: el resultado de una ventana entre el patrimonio medio. `pnlHistory` no cuenta aportaciones ni
     retiradas, así que no se confunden con rentabilidad.
  4. `tabla` y `persistencia`: el universo del plan y los dos criterios (Spearman con p por permutación; el decil
     superior de A frente a un placebo en B).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

API = "https://api.hyperliquid.xyz/info"
PAUSA = 1.05                       # ~60 consultas/min: el peso de `portfolio` no está documentado (1.200/min por IP)
MUESTRA, SEMILLA = 6000, 31
MIN_PATRIMONIO = 10_000
A = (dt.date(2025, 11, 1), dt.date(2026, 4, 30))
B = (dt.date(2026, 5, 1), dt.date(2026, 10, 30))


# ── 1. la muestra ────────────────────────────────────────────────────────────
def muestra(filas: list, n: int = MUESTRA, semilla: int = SEMILLA) -> list:
    """`n` direcciones al azar de la clasificación (ordenadas antes de sortear: el orden de la API no cuenta)."""
    direcciones = sorted({f["ethAddress"].lower() for f in filas})
    return sorted(random.Random(semilla).sample(direcciones, min(n, len(direcciones))))


# ── 2. la descarga ───────────────────────────────────────────────────────────
def _post(cuerpo: dict, abrir) -> object:
    req = urllib.request.Request(API, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    return json.loads(abrir(req))


def descargar(direcciones: list, destino: pathlib.Path, abrir=None, dormir=None, pausa: float = PAUSA,
              reintentos: int = 6) -> dict:
    """Una línea por cuenta en `destino` (jsonl): {"user", "portfolio"} o {"user", "error"}. Lo ya bajado (también lo
    que dio error definitivo) no se vuelve a pedir. Devuelve {"bajadas", "errores", "ya_estaban"}."""
    abrir = abrir or (lambda req: urllib.request.urlopen(req, timeout=60).read())
    dormir = dormir or time.sleep
    hechas = set()
    if destino.exists():
        hechas = {json.loads(l)["user"] for l in destino.read_text().splitlines() if l.strip()}
    bajadas = errores = 0
    with open(destino, "a") as out:
        for u in direcciones:
            if u in hechas:
                continue
            reg = {"user": u, "error": "sin intentos"}
            for i in range(reintentos):
                dormir(pausa)
                try:
                    reg = {"user": u, "portfolio": _post({"type": "portfolio", "user": u}, abrir)}
                    break
                except urllib.error.HTTPError as e:
                    if e.code not in (429, 500, 502, 503, 504) or i == reintentos - 1:
                        reg = {"user": u, "error": f"HTTP {e.code}"}
                        break
                    dormir(min(300, 15 * 2 ** i))
            bajadas += "portfolio" in reg
            errores += "error" in reg
            out.write(json.dumps(reg) + "\n")
            out.flush()
    return {"bajadas": bajadas, "errores": errores, "ya_estaban": len(hechas)}


# ── 3. el rendimiento de una ventana ─────────────────────────────────────────
def serie(portfolio: list, clave: str) -> list:
    """[(fecha, valor)] de `allTime` (accountValueHistory o pnlHistory), ordenada."""
    d = dict(portfolio).get("allTime", {}).get(clave, [])
    return sorted((dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date(), float(v)) for t, v in d)


def _hasta(s: list, f: dt.date):
    previos = [v for d, v in s if d <= f]
    return previos[-1] if previos else None


def rendimiento(portfolio: list, ini: dt.date, fin: dt.date):
    """{"patrimonio_ini", "pnl", "roi", "activa"} de la ventana [ini, fin], o None si la cuenta no existía al empezar
    (sin ningún punto de su curva antes de `ini`). roi = resultado / patrimonio medio (el del inicio y los puntos de
    dentro); activa = su resultado se movió en la ventana."""
    av, pnl = serie(portfolio, "accountValueHistory"), serie(portfolio, "pnlHistory")
    v0, p0, p1 = _hasta(av, ini), _hasta(pnl, ini), _hasta(pnl, fin)
    if v0 is None or p0 is None or p1 is None:
        return None
    dentro = [v for d, v in av if ini < d <= fin]
    medio = float(np.mean([v0] + dentro))
    return {"patrimonio_ini": v0, "pnl": p1 - p0, "roi": (p1 - p0) / medio if medio > 0 else np.nan,
            "activa": p1 != p0}


def tabla(registros: list) -> pd.DataFrame:
    """El universo del plan: patrimonio ≥ `MIN_PATRIMONIO` al empezar A, activa en A y en B; columnas roi_a, roi_b."""
    filas = []
    for r in registros:
        if "portfolio" not in r:
            continue
        a, b = rendimiento(r["portfolio"], *A), rendimiento(r["portfolio"], *B)
        if a and b and a["patrimonio_ini"] >= MIN_PATRIMONIO and a["activa"] and b["activa"] \
                and np.isfinite(a["roi"]) and np.isfinite(b["roi"]):
            filas.append({"user": r["user"], "roi_a": a["roi"], "roi_b": b["roi"], "patrimonio_a": a["patrimonio_ini"]})
    return pd.DataFrame(filas, columns=["user", "roi_a", "roi_b", "patrimonio_a"])


# ── 4. la persistencia ───────────────────────────────────────────────────────
def spearman(x, y) -> float:
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def persistencia(t: pd.DataFrame, perms: int = 10_000, reps: int = 200, semilla: int = SEMILLA) -> dict:
    """Los dos criterios de 3A: Spearman(roi_a, roi_b) > 0 con p < 0,01 unilateral (permutación) y la mediana en B del
    decil superior de A por encima del p95 de un placebo (deciles al azar)."""
    rng = np.random.default_rng(semilla)
    x, y = t["roi_a"].to_numpy(), t["roi_b"].to_numpy()
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    nulos = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(perms)])
    p = float((1 + (nulos >= rho).sum()) / (1 + perms))
    k = max(1, int(round(len(t) * 0.10)))
    decil = float(np.median(y[np.argsort(-x)[:k]]))
    placebo = [float(np.median(rng.choice(y, size=k, replace=False))) for _ in range(reps)]
    p95 = float(np.percentile(placebo, 95))
    crit = {"1_spearman_positiva_p_001": rho > 0 and p < 0.01, "2_decil_sobre_placebo_p95": decil > p95}
    return {"n": int(len(t)), "rho": rho, "p": p, "decil": k, "decil_mediana_b": decil, "placebo_p95": p95,
            "placebo_mediana": float(np.median(placebo)), "criterios": crit,
            "cumplidos": int(sum(crit.values())), "pasa": all(crit.values())}
