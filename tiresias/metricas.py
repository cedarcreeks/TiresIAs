# -*- coding: utf-8 -*-
"""Los criterios de docs/PLAN.md, calculados: RankIC, la compra y venta simulada con costes, las reglas
ingenuas, el placebo y el bootstrap. Sin scipy: lo que hace falta, aquí y con su test.

La simulación: una señal tras el cierre de *t* se ejecuta a la APERTURA de *t+1* y se mantiene `paso` sesiones
(1 diario, 5 semanal); la rentabilidad va de apertura a apertura, con las aperturas ajustadas por dividendos
(factor adjclose/close del día). El coste se paga en cada cambio de posición. El Sharpe se mide sobre
rentabilidades SEMANALES (viernes), para que valores con calendarios distintos (el bitcoin cotiza el fin de
semana) se puedan sumar en una cartera.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ── correlaciones ────────────────────────────────────────────────────────
def spearman(a, b) -> float:
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    ok = a.notna() & b.notna()
    ra, rb = a[ok].rank().to_numpy(), b[ok].rank().to_numpy()       # empates: rango medio
    if len(ra) < 3 or ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def sin_solape(p: pd.DataFrame, H: int) -> pd.DataFrame:
    """Una fecha de cada H: con H > 1 las ventanas reales se solapan y el IC sale autocorrelacionado."""
    return p.sort_values("fecha").iloc[::H]


def bloques(n: int, largo: float, reps: int, semilla: int) -> np.ndarray:
    """Índices de bootstrap estacionario (Politis y Romano), circulares, con bloques de largo medio `largo`."""
    rng = np.random.default_rng(semilla)
    out = np.empty((reps, n), dtype=int)
    for k in range(reps):
        i = 0
        while i < n:
            ini, lg = rng.integers(n), rng.geometric(1.0 / largo)
            for j in range(min(lg, n - i)):
                out[k, i + j] = (ini + j) % n
            i += lg
    return out


def ic_remuestreado(por: dict, reps: int, semilla: int = 0) -> np.ndarray:
    """[reps, valores]: la RankIC de cada valor en cada réplica de un bootstrap estacionario CONJUNTO por semanas
    de calendario (bloques de 4, ~20 sesiones). Conjunto, porque las semanas malas lo son para todos a la vez:
    remuestrear cada valor por su lado rompe esa correlación y estrecha el intervalo (aprobaría de más). Por
    semanas, porque es el calendario común: el bitcoin cotiza en fin de semana y las bolsas no."""
    fechas = {s: pd.to_datetime(p["fecha"]) for s, p in por.items()}
    origen = min(f.min() for f in fechas.values())
    sem = {s: ((f - origen).dt.days // 7).to_numpy() for s, f in fechas.items()}
    nsem = int(max(v.max() for v in sem.values())) + 1
    filas = {s: [np.flatnonzero(v == w) for w in range(nsem)] for s, v in sem.items()}
    idx = bloques(nsem, 4.0, reps, semilla)
    out = np.empty((reps, len(por)))
    for j, (s, p) in enumerate(por.items()):
        a, b = p["r_prevista"].to_numpy(), p["r_real"].to_numpy()
        for k in range(reps):
            sel = np.concatenate([filas[s][w] for w in idx[k]])
            out[k, j] = spearman(a[sel], b[sel])
    return out


def rankic_media(preds: dict, H: int, reps: int = 2000, semilla: int = 0) -> dict:
    """RankIC de cada valor (fechas sin solape) y la media de los valores con su intervalo del 90 %."""
    por = {s: sin_solape(p, H) for s, p in preds.items()}
    ic = {s: spearman(p["r_prevista"], p["r_real"]) for s, p in por.items()}
    medias = np.nanmean(ic_remuestreado(por, reps, semilla), axis=1)
    return {"por_valor": ic, "media": float(np.nanmean(list(ic.values()))),
            "ic90": (float(np.nanpercentile(medias, 5)), float(np.nanpercentile(medias, 95)))}


# ── la simulación de compra y venta ──────────────────────────────────────
def aperturas_ajustadas(velas: pd.DataFrame) -> pd.Series:
    return velas["open"] * (velas["adjclose"] / velas["close"])


class Simulador:
    """Lo que no cambia entre simulaciones de un mismo valor (aperturas, en qué sesión rige cada decisión),
    calculado una vez: el placebo sólo baraja los valores de las decisiones.

    La curva vale, en la fecha *s*, el patrimonio a la APERTURA de *s* antes de operar: 1 en la primera apertura
    en que rige una decisión. La posición de *s* (y su coste, si cambia) se ve en *s+1*."""

    def __init__(self, velas: pd.DataFrame, fechas_decision, paso: int, coste: float):
        ap = aperturas_ajustadas(velas).to_numpy()
        self.fechas = velas.index
        self.i = self.fechas.get_indexer(pd.to_datetime(fechas_decision))
        if (self.i < 0).any():
            raise ValueError("una fecha de decisión no es sesión del valor")
        self.ini = int(self.i[0]) + 1
        self.r = (ap[1:] / ap[:-1] - 1.0)[self.ini:]                    # de la apertura s a la s+1
        self.paso, self.coste = paso, coste

    def curva(self, dentro) -> pd.Series:
        pos = np.zeros(len(self.fechas))
        for i, d in zip(self.i, np.asarray(dentro, dtype=float)):
            pos[i + 1:i + 1 + self.paso] = d
        pos = pos[self.ini:-1]
        cambio = np.abs(np.diff(pos, prepend=0.0))
        v = np.concatenate([[1.0], np.cumprod(1.0 + pos * self.r - self.coste * cambio)])
        return pd.Series(v, index=self.fechas[self.ini:])


def estrategia(velas: pd.DataFrame, decisiones: pd.Series, paso: int, coste: float) -> pd.Series:
    """Valor diario (en las aperturas) de seguir `decisiones` (índice: fecha de la decisión, valor: dentro o no).
    La decisión de *t* rige de la apertura de *t+1* a la de *t+1+paso*; sin decisión vigente, fuera."""
    return Simulador(velas, decisiones.index, paso, coste).curva(decisiones.to_numpy())


def cartera(curvas: dict) -> pd.Series:
    """A partes iguales, sin reajustar: cada curva desde 1, en el calendario de todas (rellenando hacia delante)."""
    df = pd.DataFrame({s: c / c.iloc[0] for s, c in curvas.items()}).sort_index().ffill().dropna()
    return df.mean(axis=1)


def semanales(curva: pd.Series) -> pd.Series:
    return curva.resample("W-FRI").last().pct_change().dropna()


def sharpe(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(52)) if sd > 0 else float("nan")


def cagr(curva: pd.Series) -> float:
    años = (curva.index[-1] - curva.index[0]).days / 365.25
    return float((curva.iloc[-1] / curva.iloc[0]) ** (1 / años) - 1) if años > 0 else float("nan")


def p_mejor(ra: pd.Series, rb: pd.Series, reps: int = 2000, semilla: int = 0) -> float:
    """P(Sharpe de a > Sharpe de b) por bootstrap estacionario de bloques de 4 semanas (~20 sesiones), con los
    mismos índices para las dos."""
    x = pd.concat([ra, rb], axis=1).dropna()
    idx = bloques(len(x), 4.0, reps, semilla)
    a, b = x.iloc[:, 0].to_numpy(), x.iloc[:, 1].to_numpy()
    return float(np.mean([sharpe(a[i]) > sharpe(b[i]) for i in idx]))


# ── reglas ingenuas ──────────────────────────────────────────────────────
def decisiones_kronos(p: pd.DataFrame, paso: int, umbral: float = 0.5) -> pd.Series:
    q = p.sort_values("fecha").iloc[::paso]
    return pd.Series((q["p_subida"] > umbral).to_numpy(), index=pd.to_datetime(q["fecha"]))


def decisiones_momento(velas: pd.DataFrame, fechas, n: int = 5) -> pd.Series:
    c = velas["close"]
    return pd.Series([bool(c.loc[:d].iloc[-1] > c.loc[:d].iloc[-1 - n]) for d in fechas], index=fechas)


def decisiones_media(velas: pd.DataFrame, fechas, n: int = 200) -> pd.Series:
    c = velas["close"]
    return pd.Series([bool(c.loc[:d].iloc[-1] > c.loc[:d].iloc[-n:].mean()) for d in fechas], index=fechas)


def coste_equilibrio(velas: pd.DataFrame, dec: pd.Series, paso: int, cagr_bh: float) -> float | None:
    """El coste por operación con el que la estrategia iguala el CAGR de comprar y mantener (bisección).
    None si ni gratis lo iguala."""
    if cagr(estrategia(velas, dec, paso, 0.0)) <= cagr_bh:
        return None
    lo, hi = 0.0, 0.2
    for _ in range(50):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if cagr(estrategia(velas, dec, paso, m)) > cagr_bh else (lo, m)
    return (lo + hi) / 2


# ── diagnóstico de la predicción, valor a valor ──────────────────────────
def wilson(k: int, n: int, z: float = 1.645) -> tuple:
    """Intervalo de Wilson de una proporción k/n (por defecto, del 90 %)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - m, c + m)


def acierto(p: pd.DataFrame) -> dict:
    """Cuántas veces sube cuando Kronos dice que sube (p de subida > 0,5) y cuando dice que baja, frente a la
    frecuencia con que sube sin más. Si no sabe nada, las tres salen parecidas."""
    sube, dice = (p["r_real"] > 0).to_numpy(), (p["p_subida"] > 0.5).to_numpy()
    k1, n1, k0, n0 = int(sube[dice].sum()), int(dice.sum()), int(sube[~dice].sum()), int((~dice).sum())
    return {"n": len(p), "base": float(sube.mean()), "dice_sube": float(dice.mean()),
            "sube_si_dice_sube": k1 / n1 if n1 else float("nan"), "ic_dice_sube": wilson(k1, n1), "n_dice_sube": n1,
            "sube_si_dice_baja": k0 / n0 if n0 else float("nan"), "ic_dice_baja": wilson(k0, n0), "n_dice_baja": n0}


def cobertura(p: pd.DataFrame) -> float:
    """Fracción de veces en que lo real cae entre sus percentiles 10 y 90 (bordes incluidos): un 80 % si su
    incertidumbre es honesta; menos, si se cree más seguro de lo que es."""
    return float(((p["r_real"] >= p["r_p10"]) & (p["r_real"] <= p["r_p90"])).mean())


def mae_relativo(p: pd.DataFrame) -> float:
    """Error absoluto medio de la rentabilidad prevista entre el de decir «no cambia» (prever 0). < 1, mejor."""
    return float((p["r_prevista"] - p["r_real"]).abs().mean() / p["r_real"].abs().mean())


def calibracion(p: pd.DataFrame) -> pd.DataFrame:
    """Por cada probabilidad de subida (0, 0,1… 1 con N = 10): cuántas veces, y con qué frecuencia subió de verdad,
    con su intervalo de Wilson del 90 %."""
    g = pd.DataFrame({"p": p["p_subida"].round(1), "sube": p["r_real"] > 0}).groupby("p")["sube"]
    t = pd.DataFrame({"n": g.size(), "k": g.sum().astype(int)})
    t["frecuencia"] = t["k"] / t["n"]
    ic = [wilson(k, n) for k, n in zip(t["k"], t["n"])]
    t["lo"], t["hi"] = [a for a, _ in ic], [b for _, b in ic]
    return t
