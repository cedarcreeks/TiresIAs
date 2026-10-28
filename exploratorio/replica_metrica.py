# -*- coding: utf-8 -*-
"""EXPLORATORIO (28-oct): la métrica del ARTÍCULO de Kronos, con nuestro montaje.

Su IC/RankIC no ordena valores: es la correlación, dentro de cada predicción, entre el camino previsto de H velas y el
real, en apertura, máximo, mínimo y cierre, promediada (arXiv 2508.02739; Kronos-small, media de frecuencias: IC 0,0431,
RankIC 0,0254). Con su protocolo diario (40 velas, H = 12, T = 0,6, top-p 0,9, N = 10), sobre los 5 valores.

- Control: se rehacen los MISMOS lotes y semillas que `tiresias.correr`; el cierre final medio tiene que ser
  exactamente la r_prevista guardada (si no, no es la misma predicción).
- Vara ingenua: prolongar en línea recta la tendencia de las 20 sesiones anteriores. Su correlación con el camino real es
  ±la de una recta, sin modelo.
- El artículo no dice si correlaciona precios o rentabilidades: se dan las dos (la rentabilidad, paso a paso).

    PYTHONPATH=. python exploratorio/replica_metrica.py --dir ~/tiresias_resultados/cinco --salida <json>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np
import pandas as pd

from tiresias import evaluar as E
from tiresias import metricas as X
from tiresias import modelo as M

CANALES = ["open", "high", "low", "close"]


def _corr(a, b, rango: bool) -> float:
    if np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return X.spearman(a, b) if rango else float(np.corrcoef(a, b)[0, 1])


def por_ventana(pred: np.ndarray, real: np.ndarray, c0: np.ndarray) -> dict:
    """pred, real: [H, 4] (O, H, L, C). c0: [4] la última vela vista. En precios y en rentabilidad de cada paso
    (x / c0 − 1 sería una transformación afín del precio y daría la MISMA correlación: no sería otra medida)."""
    out = {}
    pasos = lambda x: np.vstack([c0, x])[1:] / np.vstack([c0, x])[:-1] - 1      # noqa: E731
    for nombre, f in (("precios", lambda x: x), ("rentab", pasos)):
        a, b = f(pred), f(real)
        out[f"ic_{nombre}"] = float(np.nanmean([_corr(a[:, k], b[:, k], False) for k in range(4)]))
        out[f"ric_{nombre}"] = float(np.nanmean([_corr(a[:, k], b[:, k], True) for k in range(4)]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--H", type=int, default=12)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    pro = json.loads((d / "procedencia.json").read_text(encoding="utf-8"))
    tok, mod = M.cargar("small", pro["dispositivo"])
    res, H = {}, a.H
    for s in ["IDR.MC", "ACS.MC", "SPY", "3USL.MI", "BTC-EUR"]:
        t0 = time.time()
        df = pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
        guard = pd.read_csv(d / f"pred_{s}_H{H}.csv", float_precision="round_trip").set_index("fecha")["r_prevista"]
        filas, distintas = [], 0
        for trozo in E._lotes(df, H, pro["desde"], pro["lote"]):
            z = E._trayectorias_lote(tok, mod, df, s, H, pro["N"], trozo, 0.6, 0.9)
            for j, i in enumerate(trozo):
                c0f = float(df["close"].iloc[i])
                if float((z[j, :, -1, 3] / c0f - 1.0).mean()) != guard[str(df.index[i].date())]:
                    distintas += 1
                c0 = df[CANALES].iloc[i].to_numpy()
                real = df[CANALES].iloc[i + 1:i + 1 + H].to_numpy()
                kr = por_ventana(z[j].mean(axis=0)[:, :4].astype(float), real, c0)
                pend = df["close"].iloc[i] / df["close"].iloc[i - 20] - 1.0 if i >= 20 else 0.0
                recta = c0[None, :] * (1 + pend / 20 * np.arange(1, H + 1))[:, None]
                ing = por_ventana(recta, real, c0)
                filas.append({**{f"k_{k}": v for k, v in kr.items()}, **{f"n_{k}": v for k, v in ing.items()}})
        t = pd.DataFrame(filas)
        res[s] = {"ventanas": len(t), "predicciones_distintas_de_lo_guardado": distintas, **t.mean().to_dict()}
        print(f"{s}: {len(t)} ventanas, {distintas} distintas de lo guardado, Kronos RankIC precios {res[s]['k_ric_precios']:+.4f} "
              f"(ingenua {res[s]['n_ric_precios']:+.4f}) · rentab {res[s]['k_ric_rentab']:+.4f} ({res[s]['n_ric_rentab']:+.4f}) "
              f"· {time.time() - t0:.0f} s", flush=True)
    media = {k: float(np.mean([r[k] for r in res.values()])) for k in res["SPY"] if k.startswith(("k_", "n_"))}
    print("MEDIA 5 valores:", {k: round(v, 4) for k, v in media.items()})
    pathlib.Path(a.salida).expanduser().write_text(json.dumps({"por_valor": res, "media": media, "H": H}, indent=1),
                                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
