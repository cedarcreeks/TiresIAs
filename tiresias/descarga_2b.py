"""Fase 2B: la descarga de Alpaca, por partes y reanudable (docs/PLAN_FASE2.md, «Precios»).

Corre en la máquina que tiene las claves (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` en el entorno; nunca se imprimen) y
sólo necesita la biblioteca estándar y `tiresias.precios`. Lee un pedido en JSON:

    {"barras": [{"id": "...", "simbolos": [...], "desde": "AAAA-MM-DD", "hasta": "...", "modos": ["all", "raw", "tal_cual"]}],
     "acciones": [{"id": "...", "cusips": [...], "simbolos": [...], "desde": "...", "hasta": "..."}]}

y deja en el destino una parte por petición (`barras_<id>_<modo>.jsonl.gz`, `acciones_<id>.json.gz`) y un
`manifiesto.jsonl` con lo hecho y lo que se quedó sin datos. Una parte ya escrita no se vuelve a pedir.

    python -m tiresias.descarga_2b PEDIDO.json DESTINO
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import sys

from tiresias import precios as P

MODOS = {"all": ("all", None), "raw": ("raw", None), "tal_cual": ("raw", "-")}


def _escribir(ruta: pathlib.Path, texto: str):
    # un temporal por proceso: con varios trabajando sobre el mismo destino, dos que bajen la misma parte no se pisan
    tmp = ruta.with_suffix(ruta.suffix + f".{os.getpid()}.tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(texto)
    tmp.replace(ruta)                     # una parte a medias nunca queda con su nombre final


def ejecutar(pedido: dict, destino: pathlib.Path, alpaca) -> dict:
    """Ejecuta lo que falte del pedido. Devuelve {"hechas", "saltadas", "sin_datos"}."""
    destino.mkdir(parents=True, exist_ok=True)
    man = destino / "manifiesto.jsonl"
    hechas = saltadas = 0
    sin_datos = []
    for b in pedido.get("barras", []):
        # primero lo que cotizó con cada símbolo (asof=-): lo que ahí no tiene barras no existe en Alpaca, y en los
        # otros modos sólo se repiten solos los que sí las tienen (los que un lote se calla al quitar repetidos)
        con_barras = None
        for modo in sorted(b["modos"], key=lambda m: m != "tal_cual"):
            parte = destino / f"barras_{b['id']}_{modo}.jsonl.gz"
            if parte.exists():
                if modo == "tal_cual":
                    con_barras = set(_simbolos_de(parte))
                saltadas += 1
                continue
            ajuste, asof = MODOS[modo]
            antes = len(alpaca.sin_datos)
            out = alpaca.barras(b["simbolos"], b["desde"], b["hasta"], ajuste, asof,
                                solos=set() if modo == "tal_cual" else con_barras)
            if modo == "tal_cual":
                con_barras = set(out)
            faltan = [x[0] for x in alpaca.sin_datos[antes:]]
            lineas = (json.dumps({"s": s, "f": f.isoformat(), "c": c, "v": v})
                      for s, serie in sorted(out.items()) for f, (c, v) in sorted(serie.items()))
            _escribir(parte, "\n".join(lineas))
            with open(man, "a") as m:
                m.write(json.dumps({"parte": parte.name, "simbolos": len(b["simbolos"]), "con_datos": len(out),
                                    "barras": sum(len(x) for x in out.values()), "sin_datos": faltan}) + "\n")
            sin_datos += [(modo, s) for s in faltan]
            hechas += 1
    for a in pedido.get("acciones", []):
        parte = destino / f"acciones_{a['id']}.json.gz"
        if parte.exists():
            saltadas += 1
            continue
        out = alpaca.acciones(a["desde"], a["hasta"], cusips=a.get("cusips", []), simbolos=a.get("simbolos", []))
        _escribir(parte, json.dumps(out))
        with open(man, "a") as m:
            m.write(json.dumps({"parte": parte.name, "registros": sum(len(v) for v in out.values())}) + "\n")
        hechas += 1
    return {"hechas": hechas, "saltadas": saltadas, "sin_datos": sin_datos}


def _simbolos_de(parte: pathlib.Path) -> list:
    with gzip.open(parte, "rt", encoding="utf-8") as f:
        return sorted({json.loads(linea)["s"] for linea in f if linea.strip()})


def leer_barras(destino: pathlib.Path, modo: str) -> dict:
    """{símbolo: {fecha: (cierre, volumen)}} de todas las partes de ese modo (lo que lee `precios.rentabilidades`)."""
    import datetime as dt
    out = {}
    for parte in sorted(destino.glob(f"barras_*_{modo}.jsonl.gz")):
        with gzip.open(parte, "rt", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    x = json.loads(linea)
                    out.setdefault(x["s"], {})[dt.date.fromisoformat(x["f"])] = (x["c"], x["v"])
    return out


def leer_acciones(destino: pathlib.Path) -> dict:
    """{tipo: [registro]} de todas las partes, sin duplicados (`id`)."""
    out, vistos = {}, set()
    for parte in sorted(destino.glob("acciones_*.json.gz")):
        with gzip.open(parte, "rt", encoding="utf-8") as f:
            for k, v in json.load(f).items():
                for d in v:
                    clave = d.get("id") or json.dumps(d, sort_keys=True)
                    if clave not in vistos:
                        vistos.add(clave)
                        out.setdefault(k, []).append(d)
    return out


if __name__ == "__main__":
    pedido, destino = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2]).expanduser()
    a = P.Alpaca(os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"])
    r = ejecutar(pedido, destino, a)
    print(f"{a.peticiones} peticiones; partes hechas {r['hechas']}, ya estaban {r['saltadas']}; "
          f"sin datos ni pedidos solos: {len(r['sin_datos'])}")
