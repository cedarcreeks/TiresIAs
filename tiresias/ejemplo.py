# -*- coding: utf-8 -*-
"""Las N trayectorias de una predicción ya evaluada, para enseñarla: el último caso completo de cada valor
(elegido por regla, no por cómo salió), rehecho con su lote y su semilla y comprobado contra lo guardado.

    python -m tiresias.ejemplo --dir ~/tiresias_resultados/cinco --simbolos SPY 3USL.MI IDR.MC --H 5
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pandas as pd
import torch

from tiresias import evaluar as E
from tiresias import modelo as M


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--simbolos", nargs="+", required=True)
    ap.add_argument("--H", type=int, default=5)
    ap.add_argument("--modelo", default="small")
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    pro = json.loads((d / "procedencia.json").read_text(encoding="utf-8"))
    if pro["torch"] != torch.__version__.split("+")[0]:
        raise SystemExit(f"⛔ torch {torch.__version__} y las predicciones se hicieron con {pro['torch']}")
    tok, mod = M.cargar(a.modelo, pro["dispositivo"])
    out = {"H": a.H, "dispositivo": pro["dispositivo"], "valores": {}}
    for s in a.simbolos:
        df = pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
        p = pd.read_csv(d / f"pred_{s}_H{a.H}.csv", float_precision="round_trip").sort_values("fecha")
        fila = p.iloc[-1]
        z = E.muestras(tok, mod, df, s, a.H, fila["fecha"], N=pro["N"], desde=pro["desde"], lote=pro["lote"])
        c0 = float(df.loc[fila["fecha"], "close"])
        media = float((z[:, -1, 3] / c0 - 1.0).mean())
        if media != fila["r_prevista"]:
            raise SystemExit(f"⛔ {s} {fila['fecha']}: la media rehecha ({media!r}) no es la guardada ({fila['r_prevista']!r})")
        i = int(df.index.get_loc(pd.Timestamp(fila["fecha"])))  # type: ignore[arg-type]
        out["valores"][s] = {"fecha": fila["fecha"], "cierre": c0, "r_prevista": media, "p_subida": float(fila["p_subida"]),
                             "fechas_futuras": [str(x.date()) for x in df.index[i + 1:i + 1 + a.H]],
                             "trayectorias": z[:, :, 3].astype(float).round(6).tolist(),
                             "reales": df["close"].iloc[i + 1:i + 1 + a.H].round(6).tolist()}
        print(f"{s} {fila['fecha']}: {pro['N']} trayectorias, media {media:+.4%} = la guardada (exacta)")
    (d / f"ejemplo_H{a.H}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
