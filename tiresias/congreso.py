"""Fase 3C: las operaciones declaradas de los congresistas de EE. UU. (docs/PLAN_FASE3.md, apartado 3C).

  1. `indice`: las declaraciones de operaciones (PTR, tipo «P») del índice anual del Clerk de la Cámara.
  2. `descargar`: los PDF de esas declaraciones, reanudable y despacio (una por segundo).
Los datos no entran nunca en el repositorio.
"""
from __future__ import annotations

import pathlib
import time
import urllib.error
import urllib.request
import zipfile

BASE = "https://disclosures-clerk.house.gov/public_disc"
PAUSA = 1.0


def indice(zip_anual: pathlib.Path) -> list:
    """[{"apellido", "nombre", "distrito", "presentado", "docid", "anio"}] de las PTR del índice anual (`AAAAFD.zip`)."""
    anio = zip_anual.name[:4]
    with zipfile.ZipFile(zip_anual) as z:
        lineas = z.read(f"{anio}FD.txt").decode("utf-8", errors="replace").splitlines()
    cab = lineas[0].split("\t")
    out = []
    for linea in lineas[1:]:
        c = dict(zip(cab, linea.split("\t")))
        if c.get("FilingType") == "P" and c.get("DocID"):
            out.append({"apellido": c["Last"], "nombre": c["First"], "distrito": c["StateDst"],
                        "presentado": c["FilingDate"], "docid": c["DocID"].strip(), "anio": anio})
    return out


def descargar(ptrs: list, destino: pathlib.Path, abrir=None, dormir=None, pausa: float = PAUSA) -> dict:
    """Cada PDF a `destino/<año>/<docid>.pdf`; lo que ya está no se pide. Un 404 se apunta en `faltan.txt` y no se
    repite. Devuelve {"bajados", "ya_estaban", "faltan"}."""
    abrir = abrir or (lambda req: urllib.request.urlopen(req, timeout=60).read())
    dormir = dormir or time.sleep
    faltan_f = destino / "faltan.txt"
    faltan = set(faltan_f.read_text().split()) if faltan_f.exists() else set()
    bajados = ya = 0
    for p in ptrs:
        f = destino / p["anio"] / f"{p['docid']}.pdf"
        if f.exists() or p["docid"] in faltan:
            ya += 1
            continue
        dormir(pausa)
        req = urllib.request.Request(f"{BASE}/ptr-pdfs/{p['anio']}/{p['docid']}.pdf",
                                     headers={"User-Agent": "TiresIAs research (github.com/cedarcreeks/TiresIAs)"})
        try:
            datos = abrir(req)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                faltan.add(p["docid"])
                with open(faltan_f, "a") as m:
                    m.write(p["docid"] + "\n")
                continue
            raise
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".pdf.tmp")
        tmp.write_bytes(datos)
        tmp.replace(f)
        bajados += 1
    return {"bajados": bajados, "ya_estaban": ya, "faltan": len(faltan)}
