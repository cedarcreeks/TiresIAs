# -*- coding: utf-8 -*-
"""Lanza las predicciones de una lista de valores y las guarda fuera del repo, con su procedencia.

    python -m tiresias.correr --simbolos IDR.MC ACS.MC SPY 3USL.MI BTC-EUR --H 1 5 12 --fin 2026-10-23 \
        --dia 2026-10-27 --dispositivo cpu --salida ~/tiresias_resultados/cinco
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import platform
import subprocess
import time

import torch

from tiresias import datos as D
from tiresias import evaluar as E
from tiresias import modelo as M


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simbolos", nargs="+", required=True)
    ap.add_argument("--H", nargs="+", type=int, required=True)
    ap.add_argument("--fin", required=True)
    ap.add_argument("--dia", default=None, help="día de la descarga (la caché); por defecto, hoy")
    ap.add_argument("--dispositivo", default="cpu")
    ap.add_argument("--N", type=int, default=10)
    ap.add_argument("--lote", type=int, default=100)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    sal = pathlib.Path(a.salida).expanduser()
    sal.mkdir(parents=True, exist_ok=True)
    tok, mod = M.cargar("small", a.dispositivo)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=pathlib.Path(__file__).resolve().parent.parent).stdout.strip()
    meta = {"commit": commit, "dispositivo": a.dispositivo, "torch": torch.__version__, "maquina": platform.node(),
            "fin": a.fin, "dia_descarga": a.dia or dt.date.today().isoformat(), "N": a.N, "lote": a.lote,
            "L": E.L, "desde": E.DESDE, "inicio": dt.datetime.now().isoformat(timespec="seconds"), "tiempos": {}}
    for s in a.simbolos:
        df = D.velas(s, a.fin, a.dia)
        df.to_csv(sal / f"velas_{s}.csv")
        for H in a.H:
            t0 = time.perf_counter()
            p = E.predecir(tok, mod, df, s, H, N=a.N, lote=a.lote)
            p.to_csv(sal / f"pred_{s}_H{H}.csv", index=False)
            meta["tiempos"][f"{s} H{H}"] = round(time.perf_counter() - t0, 1)
            print(f"{s} H={H}: {len(p)} fechas en {meta['tiempos'][f'{s} H{H}']} s", flush=True)
    meta["fin_ejecucion"] = dt.datetime.now().isoformat(timespec="seconds")
    (sal / "procedencia.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
