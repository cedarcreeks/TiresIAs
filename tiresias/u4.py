# -*- coding: utf-8 -*-
"""U4 (docs/PLAN_UTILIDAD.md): la receta de trading de sus autores, con el modelo reentrenado y, de comparación, el original.

Puntuación (su `qlib_test.py`, «last»): cada sesión, 90 velas, 10 de horizonte, 5 futuros (T 0,6, top-p 0,9); el cierre
previsto a 10 sesiones (media de los futuros) menos el último, en unidades de la ventana: (previsto − cierre) / (desviación
del cierre en la ventana + 1e-5), que es lo mismo que su diferencia en el espacio normalizado.

Cartera (su `TopkDropoutStrategy`, leída en el código de Qlib): 50 valores, venta de las tenencias que caen entre las 5
peores de (tenencias ∪ aspirantes) si llevan ≥ 5 sesiones, compra de los mejores aspirantes con efectivo × 0,95 / nº; la
señal del cierre de t se opera a la apertura de t+1; 0,10 % al comprar y 0,15 % al vender. Simplificaciones declaradas:
acciones fraccionarias (Qlib redondea a lotes de 100, de China) y sin el coste mínimo (5 sobre una cuenta de 10⁸).

    python -m tiresias.u4 predecir --dir <velas> --u4 <modelos> --modelo reentrenado --salida <dir> --dispositivo cuda
    python -m tiresias.u4 evaluar --dir <velas> --pred <dir de predicciones>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np
import pandas as pd

from tiresias import metricas as X
from tiresias import modelo as M
from tiresias import ronda2 as R2
from tiresias import transversal as T

L, H, N = 90, 10, 5
DESDE = "2024-07-01"
K, N_DROP, PERMANENCIA, RIESGO = 50, 5, 5, 0.95
C_COMPRA, C_VENTA = 0.0010, 0.0015


# ── modelos y puntuación ─────────────────────────────────────────────────
TOPE_VRAM = 0.85


def vigilar_vram(dispositivo: str) -> float:
    """Fracción de la memoria de vídeo que llegó a reservar PyTorch. En Windows, pasarse NO da error de memoria: el
    controlador desborda a la RAM del sistema y todo va 6–8 veces más lento (28-oct: lote 120 a 687 ms por serie, lote
    60 a 85). Por eso se para en vez de seguir."""
    import torch
    if not dispositivo.startswith("cuda"):
        return 0.0
    usado = torch.cuda.max_memory_reserved() / torch.cuda.get_device_properties(0).total_memory
    if usado > TOPE_VRAM:
        raise SystemExit(f"⛔ la memoria de vídeo llegó al {usado:.0%} (tope {TOPE_VRAM:.0%}): baja el lote")
    return usado
def cargar(nombre: str, u4: pathlib.Path | None, dispositivo: str):
    if nombre == "original":
        return M.cargar("small", dispositivo)
    from model import Kronos, KronosTokenizer
    tok = KronosTokenizer.from_pretrained(str(u4 / "tokenizador_mejor")).eval().to(dispositivo)
    mod = Kronos.from_pretrained(str(u4 / "predictor_mejor")).eval().to(dispositivo)
    return tok, mod


def puntuar(tok, mod, df: pd.DataFrame, simbolo: str, posiciones: list, etiqueta: str, lote: int = 120) -> pd.DataFrame:
    """Una fila por posición: la puntuación «last» y, por referencia, la rentabilidad prevista a 10 sesiones."""
    entrada = ["open", "high", "low", "close", "volume"]
    filas = []
    for k in range(0, len(posiciones), lote):
        trozo = posiciones[k:k + lote]
        dfs = [df.iloc[i - L + 1:i + 1][entrada].reset_index(drop=True) for i in trozo]
        th = [pd.Series(df.index[i - L + 1:i + 1]) for i in trozo]
        # el calendario futuro: las 10 sesiones siguientes si existen; si no (final de los datos), días hábiles
        tf = [pd.Series(df.index[i + 1:i + 1 + H]) if i + H < len(df)
              else pd.Series(pd.bdate_range(df.index[i] + pd.Timedelta(days=1), periods=H)) for i in trozo]
        z = M.trayectorias(tok, mod, dfs, th, tf, H, N, T=0.6, top_p=0.9,
                           seed=M.semilla(simbolo, H, N, str(df.index[trozo[0]].date()), etiqueta))
        for j, i in enumerate(trozo):
            c0, sd = float(df["close"].iloc[i]), float(df["close"].iloc[i - L + 1:i + 1].std(ddof=0))
            prev = float(z[j, :, -1, 3].mean())
            filas.append({"fecha": str(df.index[i].date()), "puntuacion": (prev - c0) / (sd + 1e-5),
                          "r_prevista": prev / c0 - 1.0})
    return pd.DataFrame(filas)


def ic_camino(prev: np.ndarray, real: np.ndarray) -> tuple:
    """La métrica de su artículo (apéndice D): en UNA predicción, la correlación a lo largo del horizonte entre el camino
    previsto y el real, en cada canal de precio (apertura, máximo, mínimo, cierre), y la media de los cuatro. `prev` y
    `real`: [H, 4]. Un canal constante no tiene correlación y no cuenta."""
    ic, ric = [], []
    for c in range(4):
        p, r = prev[:, c], real[:, c]
        if np.std(p) == 0 or np.std(r) == 0:
            continue
        ic.append(float(np.corrcoef(p, r)[0, 1]))
        ric.append(X.spearman(p, r))
    return (float(np.mean(ic)), float(np.mean(ric))) if ic else (np.nan, np.nan)


def caminos(tok, mod, df: pd.DataFrame, simbolo: str, posiciones: list, etiqueta: str, lote: int = 60) -> list:
    """(fecha, IC, RankIC) de su métrica en cada posición, con la configuración de U4 (90 velas, 10 de horizonte, 5
    futuros, T 0,6, top-p 0,9) y el camino real de las 10 sesiones siguientes."""
    precios = ["open", "high", "low", "close"]
    out = []
    for k in range(0, len(posiciones), lote):
        trozo = posiciones[k:k + lote]
        dfs = [df.iloc[i - L + 1:i + 1][precios + ["volume"]].reset_index(drop=True) for i in trozo]
        th = [pd.Series(df.index[i - L + 1:i + 1]) for i in trozo]
        tf = [pd.Series(df.index[i + 1:i + 1 + H]) for i in trozo]
        z = M.trayectorias(tok, mod, dfs, th, tf, H, N, T=0.6, top_p=0.9,
                           seed=M.semilla(simbolo, H, N, str(df.index[trozo[0]].date()), etiqueta))
        for j, i in enumerate(trozo):
            real = df.iloc[i + 1:i + 1 + H][precios].to_numpy(dtype=float)
            out.append((str(df.index[i].date()), *ic_camino(z[j, :, :, :4].mean(axis=0), real)))
    return out


# ── TopkDropout ──────────────────────────────────────────────────────────
def topk_dropout(S: np.ndarray, A: np.ndarray, Ccl: np.ndarray, k: int = K, n_drop: int = N_DROP,
                 permanencia: int = PERMANENCIA, riesgo: float = RIESGO, c_compra: float = C_COMPRA,
                 c_venta: float = C_VENTA) -> dict:
    """S[t, j]: puntuación tras el cierre de t (NaN si no hay). A[t, j]: apertura ajustada; Ccl[t, j]: cierre ajustado.
    La señal de t decide las órdenes a la apertura de t+1. Devuelve el valor diario al cierre y la rotación."""
    T_, J = S.shape
    acciones = np.zeros(J)
    dias = np.zeros(J, dtype=int)
    efectivo, valor = 1.0, np.full(T_, np.nan)
    valor[0] = 1.0
    ultimo = np.where(np.isnan(Ccl[0]), 0.0, Ccl[0])          # el último cierre conocido: un día sin dato no vale 0
    rotacion = 0.0
    for t in range(1, T_):
        s = S[t - 1]
        tiene = np.flatnonzero(acciones > 0)
        if not np.isnan(s).all():
            sc = np.where(np.isnan(s), -np.inf, s)
            last = tiene[np.argsort(-sc[tiene], kind="stable")]
            fuera = np.setdiff1d(np.flatnonzero(~np.isnan(s)), tiene)
            today = fuera[np.argsort(-sc[fuera], kind="stable")][:max(0, n_drop + k - len(last))]
            comb = np.concatenate([last, today])
            comb = comb[np.argsort(-sc[comb], kind="stable")]
            peores = set(comb[-n_drop:].tolist()) if n_drop > 0 else set()
            vender = [j for j in last if j in peores]
            comprar = today[:len(vender) + k - len(last)]
            for j in vender:
                if dias[j] < permanencia or np.isnan(A[t, j]):
                    continue
                v = acciones[j] * A[t, j]
                efectivo += v * (1 - c_venta)
                rotacion += v
                acciones[j], dias[j] = 0.0, 0
            comprables = [j for j in comprar if not np.isnan(A[t, j])]
            if comprables:
                cada = efectivo * riesgo / len(comprables)
                for j in comprables:
                    acciones[j] += cada * (1 - c_compra) / A[t, j]
                    efectivo -= cada
                    rotacion += cada
        tiene = acciones > 0
        dias[tiene] += 1
        ultimo = np.where(np.isnan(Ccl[t]), ultimo, Ccl[t])
        valor[t] = efectivo + float(np.sum(acciones * ultimo))
    return {"valor": valor, "rotacion_anual": rotacion / (T_ / 252)}


# ── matrices y evaluación ────────────────────────────────────────────────
def matrices(d: pathlib.Path, dp: pathlib.Path, simbolos: list) -> tuple:
    cal = T.leer_velas(d, T.CALENDARIO).index
    cal = cal[cal >= pd.Timestamp(DESDE)]
    S = np.full((len(cal), len(simbolos)), np.nan)
    A, C = S.copy(), S.copy()
    for j, s in enumerate(simbolos):
        v = T.leer_velas(d, s).reindex(cal)
        aj = v["adjclose"] / v["close"]
        A[:, j], C[:, j] = (v["open"] * aj).to_numpy(), v["adjclose"].to_numpy()
        p = pd.read_csv(dp / f"pred_{s}.csv", float_precision="round_trip")
        S[:, j] = pd.Series(p["puntuacion"].to_numpy(), index=pd.to_datetime(p["fecha"])).reindex(cal).to_numpy()
    return cal, S, A, C


def rankic_10(S: np.ndarray, A: np.ndarray, minimo: int = 100) -> np.ndarray:
    """Cada 10 sesiones: RankIC entre la puntuación de t y la rentabilidad de apertura (t+1) a apertura (t+11)."""
    out = []
    for t in range(0, len(S) - 1 - H, H):
        r = A[t + 1 + H] / A[t + 1] - 1.0
        ok = ~np.isnan(S[t]) & ~np.isnan(r)
        out.append(X.spearman(S[t, ok], r[ok]) if ok.sum() >= minimo else np.nan)
    return np.array(out)


def evaluar(d: pathlib.Path, dp: pathlib.Path, placebos: int = 200) -> dict:
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    cal, S, A, C = matrices(d, dp, simbolos)
    rt = R2.resumen_t(rankic_10(S, A))
    car = topk_dropout(S, A, C)
    v = pd.Series(car["valor"], index=cal)
    r_car = v.pct_change().dropna()
    r_todos = pd.Series(np.nanmean(C[1:] / C[:-1] - 1.0, axis=1), index=cal[1:])     # partes iguales, sin coste
    exceso = (r_car - r_todos).dropna()
    sem = exceso.resample("W-FRI").sum()
    idx = X.bloques(len(sem), 4.0, 2000, 0)
    p_exceso = float(np.mean([sem.to_numpy()[i].mean() > 0 for i in idx]))
    sh = lambda r: float(r.mean() / r.std(ddof=1) * np.sqrt(252))         # noqa: E731
    rng = np.random.default_rng(20261028)
    plac = []
    for _ in range(placebos):
        Q = T.barajar_por_valor(S, rng)
        plac.append(sh(pd.Series(topk_dropout(Q, A, C)["valor"]).pct_change().dropna()))
    p95 = float(np.percentile(plac, 95))
    años = (cal[-1] - cal[0]).days / 365.25
    return {"rankic_10": rt, "sharpe_cartera": sh(r_car), "sharpe_todos": sh(r_todos), "p_exceso_positivo": p_exceso,
            "cagr_cartera": float(v.iloc[-1] ** (1 / años) - 1), "cagr_todos": float((1 + r_todos).prod() ** (1 / años) - 1),
            "rotacion_anual": car["rotacion_anual"], "placebo_p50": float(np.median(plac)), "placebo_p95": p95,
            "pasa_economico": bool(p_exceso >= 0.9 and sh(r_car) > p95)}


# ── CLI ──────────────────────────────────────────────────────────────────
def _predecir(a) -> int:
    d, sal = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.salida).expanduser()
    sal.mkdir(parents=True, exist_ok=True)
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    tok, mod = cargar(a.modelo, pathlib.Path(a.u4).expanduser() if a.u4 else None, a.dispositivo)
    for k, s in enumerate(simbolos, 1):
        f = sal / f"pred_{s}.csv"
        if f.exists():
            continue
        t0 = time.time()
        df = T.leer_velas(d, s)
        pos = [i for i, x in enumerate(df.index) if x >= pd.Timestamp(DESDE) and i >= L - 1]
        pos = pos[::a.cada]
        p = puntuar(tok, mod, df, s, pos, a.modelo, a.lote)
        vigilar_vram(a.dispositivo)                       # tras el primer valor ya se sabe: si se pasa, se para
        p.to_csv(f.with_suffix(".tmp"), index=False)
        f.with_suffix(".tmp").replace(f)
        print(f"{k}/{len(simbolos)} {s}: {len(p)} fechas en {time.time() - t0:.1f} s", flush=True)
    return 0


def _medir(a) -> int:
    d = pathlib.Path(a.dir).expanduser()
    tok, mod = cargar(a.modelo, pathlib.Path(a.u4).expanduser() if a.u4 else None, a.dispositivo)
    df = T.leer_velas(d, a.simbolo)
    pos = [i for i, x in enumerate(df.index) if x >= pd.Timestamp(DESDE) and i >= L - 1]
    n_valores = len([s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO])
    for lote in a.lotes:
        puntuar(tok, mod, df, a.simbolo, pos[:lote], a.modelo, lote)              # calentar
        vram = vigilar_vram(a.dispositivo)
        t0 = time.time()
        puntuar(tok, mod, df, a.simbolo, pos, a.modelo, lote)
        s = (time.time() - t0) / len(pos)
        print(f"lote {lote}: {s * 1000:.0f} ms por serie, memoria de vídeo {vram:.0%} · {n_valores} valores × "
              f"{len(pos)} sesiones ≈ {s * n_valores * len(pos) / 3600:.1f} h", flush=True)
    return 0


def comparar(d: pathlib.Path, reentrenado: pathlib.Path, original: pathlib.Path, placebos: int = 200) -> dict:
    """Exploratorio, fuera de Holm: el original se predijo cada 10 sesiones (coste de la RTX) y su cartera opera 10 veces
    menos. Aquí el reentrenado también, sólo en esas fechas, y cada cartera con su placebo (sus puntuaciones barajadas
    entre fechas): si el placebo gana, lo que rinde es la inclinación fija por valor, no la señal de cada día."""
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    cal, Sr, A, C = matrices(d, reentrenado, simbolos)
    So = matrices(d, original, simbolos)[1]
    años = (cal[-1] - cal[0]).days / 365.25
    sh = lambda v: float((lambda r: r.mean() / r.std(ddof=1) * np.sqrt(252))(pd.Series(v).pct_change().dropna()))  # noqa: E731
    out = {}
    for nombre, S in (("reentrenado_cada_sesion", Sr), ("reentrenado_cada_10", np.where(np.isnan(So), np.nan, Sr)),
                      ("original_cada_10", So)):
        c = topk_dropout(S, A, C)
        rng = np.random.default_rng(20261028)
        plac = [sh(topk_dropout(T.barajar_por_valor(S, rng), A, C)["valor"]) for _ in range(placebos)]
        out[nombre] = {"sharpe": sh(c["valor"]), "cagr": float(c["valor"][-1] ** (1 / años) - 1),
                       "rotacion_anual": c["rotacion_anual"], "placebo_p50": float(np.median(plac)),
                       "placebo_p95": float(np.percentile(plac, 95))}
    return out


def _camino(a) -> int:
    """Su métrica con el reentrenado y con el original, en los mismos valores y fechas (una muestra fija de valores y
    las fechas de 10 en 10, como el RankIC de U4). La misma semilla para los dos: el ruido del muestreo se empareja."""
    d, u4 = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.u4).expanduser()
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    muestra = sorted(np.random.default_rng(20261029).choice(simbolos, size=min(a.valores, len(simbolos)), replace=False))
    modelos = {m: cargar(m, u4, a.dispositivo) for m in ("reentrenado", "original")}
    filas, t0 = [], time.time()
    for k, s in enumerate(muestra, 1):
        df = T.leer_velas(d, s)
        pos = [i for i, x in enumerate(df.index) if x >= pd.Timestamp(DESDE) and i >= L - 1 and i + H < len(df)][::H]
        for m, (tok, mod) in modelos.items():
            filas += [{"valor": s, "modelo": m, "fecha": f, "ic": ic, "rankic": ric}
                      for f, ic, ric in caminos(tok, mod, df, s, pos, "camino", a.lote)]
        print(f"{k}/{len(muestra)} {s}: {len(pos)} fechas, {time.time() - t0:.0f} s", flush=True)
    p = pd.DataFrame(filas)
    p.to_csv(u4 / "camino.csv", index=False)
    por_fecha = p.pivot_table(index="fecha", columns="modelo", values=["ic", "rankic"], aggfunc="mean")
    res: dict = {"valores": len(muestra), "predicciones_por_modelo": int((p["modelo"] == "original").sum())}
    for met in ("ic", "rankic"):
        dif = (por_fecha[(met, "reentrenado")] - por_fecha[(met, "original")]).dropna()
        res[met] = {**{m: float(p.loc[p["modelo"] == m, met].mean()) for m in ("reentrenado", "original")},
                    "diferencia": R2.resumen_t(dif.to_numpy())}          # t con las fechas como unidad (no los valores)
    (u4 / "camino.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("predecir")
    p.add_argument("--dir", required=True)
    p.add_argument("--u4", default="")
    p.add_argument("--modelo", choices=["reentrenado", "original"], required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--dispositivo", default="cuda")
    p.add_argument("--lote", type=int, default=60)          # 120 desborda los 6 GB de la RTX (medido)
    p.add_argument("--cada", type=int, default=1)
    e = sub.add_parser("evaluar")
    e.add_argument("--dir", required=True)
    e.add_argument("--pred", required=True)
    e.add_argument("--placebos", type=int, default=200)
    m = sub.add_parser("medir")
    m.add_argument("--dir", required=True)
    m.add_argument("--u4", default="")
    m.add_argument("--modelo", choices=["reentrenado", "original"], required=True)
    m.add_argument("--simbolo", default="AAPL")
    m.add_argument("--lotes", nargs="+", type=int, default=[120, 300])
    m.add_argument("--dispositivo", default="cuda")
    c = sub.add_parser("camino")
    c.add_argument("--dir", required=True)
    c.add_argument("--u4", required=True)
    c.add_argument("--valores", type=int, default=100)
    c.add_argument("--lote", type=int, default=60)
    c.add_argument("--dispositivo", default="mps")
    k = sub.add_parser("comparar")
    k.add_argument("--dir", required=True)
    k.add_argument("--reentrenado", required=True)
    k.add_argument("--original", required=True)
    k.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    if a.orden == "comparar":
        r = comparar(*(pathlib.Path(x).expanduser() for x in (a.dir, a.reentrenado, a.original)))
        pathlib.Path(a.salida).expanduser().write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(json.dumps(r, indent=1))
        return 0
    if a.orden == "camino":
        return _camino(a)
    if a.orden == "medir":
        return _medir(a)
    if a.orden == "predecir":
        return _predecir(a)
    r = evaluar(pathlib.Path(a.dir).expanduser(), pathlib.Path(a.pred).expanduser(), a.placebos)
    (pathlib.Path(a.pred).expanduser() / "u4.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
