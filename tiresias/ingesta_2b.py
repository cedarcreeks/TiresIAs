"""Fase 2B: de los zips de la SEC a tablas (docs/PLAN_FASE2.md, «2B · Los datos»).

  1. `ftd`: la traducción CUSIP → símbolo con fecha de todos los ficheros de fails-to-deliver, con el recuento de cada
     uno contra el que declara (`gestores.leer_ftd` falla si no cuadra).
  2. `trece_f`: un parquet por zip de 13F (`gestores.leer_13f`), reanudable: si el parquet ya existe y su origen tiene
     el mismo SHA-256, no se vuelve a leer.
  3. `posiciones`: todas juntas, un original por gestor y periodo (el primero presentado, también entre ficheros) y
     sólo lo presentado desde `DESDE`.
Los datos de la SEC no entran nunca en el repositorio.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile

import pandas as pd

from tiresias import gestores as G

DESDE = pd.Timestamp("2016-01-01")


def _sha256(ruta: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ── 1. FTD ───────────────────────────────────────────────────────────────────
def ftd(rutas: list) -> tuple:
    """(tabla (cusip, simbolo, fecha) sin duplicados, [informe por fichero])."""
    partes, informe = [], []
    for r in sorted(rutas):
        with zipfile.ZipFile(r) as z:
            # uno solo, con o sin extensión (desde mediados de 2022 algunos vienen sin «.txt»); si hay varios, un .txt
            todos = z.namelist()
            miembros = todos if len(todos) == 1 else [m for m in todos if m.lower().endswith(".txt")]
            if len(miembros) != 1:
                raise ValueError(f"{r.name}: se esperaba un fichero de datos y hay {todos}")
            texto = z.read(miembros[0]).decode("latin-1")
        t = G.leer_ftd(texto)
        partes.append(t)
        informe.append({"fichero": r.name, "filas": len(t), "declaradas": t.attrs["declaradas"],
                        "desde": t["fecha"].min(), "hasta": t["fecha"].max()})
    tabla = pd.concat(partes, ignore_index=True).drop_duplicates().sort_values(["cusip", "fecha"]).reset_index(drop=True)
    return tabla, informe


# ── 2. 13F ───────────────────────────────────────────────────────────────────
def trece_f(rutas: list, destino: pathlib.Path) -> list:
    """Un parquet por zip en `destino`, con `<nombre>.json` al lado (SHA-256 del origen y recuentos)."""
    destino.mkdir(parents=True, exist_ok=True)
    out = []
    for r in sorted(rutas):
        pq, meta = destino / (r.stem + ".parquet"), destino / (r.stem + ".json")
        sha = _sha256(r)
        if pq.exists() and meta.exists() and json.loads(meta.read_text()).get("sha256") == sha:
            out.append(pq)
            continue
        p = G.leer_13f(r)
        p.to_parquet(pq, index=False)
        meta.write_text(json.dumps({"origen": r.name, "sha256": sha, "posiciones": len(p),
                                    "gestores": int(p["cik"].nunique()), "13f": int(p["accesion"].nunique()),
                                    "presentado": [str(p["presentado"].min().date()), str(p["presentado"].max().date())]}))
        out.append(pq)
    return out


# ── 3. todas las posiciones ──────────────────────────────────────────────────
def posiciones(parquets: list, desde: pd.Timestamp = DESDE) -> pd.DataFrame:
    """Las posiciones de todos los ficheros: un original por (gestor, periodo), el primero presentado, y desde
    `desde`. Entre ficheros también puede repetirse un original (presentado dos veces): cuenta el primero."""
    p = pd.concat([pd.read_parquet(f) for f in parquets], ignore_index=True)
    p = p[p["presentado"] >= desde]
    primeros = (p.drop_duplicates("accesion")[["accesion", "cik", "periodo", "presentado"]]
                .sort_values(["presentado", "accesion"]).drop_duplicates(["cik", "periodo"], keep="first"))
    return p[p["accesion"].isin(set(primeros["accesion"]))].reset_index(drop=True)
