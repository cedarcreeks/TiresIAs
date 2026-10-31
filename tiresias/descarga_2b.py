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
          f"sin datos ni pedidos solos: {len(r['sin_datos'])}; inválidos para Alpaca: {sorted(set(a.invalidos))}")


# ── series compactas: 75 M de barras no caben como diccionarios de Python ─────
from collections.abc import Mapping  # noqa: E402


class SeriesCompactas(Mapping):
    """{símbolo: {fecha: (cierre, volumen)}} como `leer_barras`, pero guardado en columnas (fecha ordinal, cierre,
    volumen): ~20 B por barra en vez de ~200. Cada símbolo se convierte al formato de diccionario sólo cuando se pide."""

    def __init__(self, tabla):
        import numpy as np
        t = tabla.sort_values(["s", "d"], kind="stable").reset_index(drop=True)
        self._d = t["d"].to_numpy(dtype=np.int32)
        self._c = t["c"].to_numpy(dtype=np.float64)
        self._v = t["v"].to_numpy(dtype=np.int64)
        s = t["s"].to_numpy()
        cortes = np.flatnonzero(s[1:] != s[:-1]) + 1 if len(s) else np.array([], dtype=int)
        ini = np.concatenate([[0], cortes]) if len(s) else np.array([], dtype=int)
        fin = np.concatenate([cortes, [len(s)]]) if len(s) else np.array([], dtype=int)
        self._idx = {s[i]: (int(i), int(j)) for i, j in zip(ini, fin)}

    def __getitem__(self, simbolo):
        import datetime as dt
        i, j = self._idx[simbolo]
        return {dt.date.fromordinal(int(d)): (float(c), int(v))
                for d, c, v in zip(self._d[i:j], self._c[i:j], self._v[i:j])}

    def __contains__(self, simbolo):
        return simbolo in self._idx

    def __iter__(self):
        return iter(self._idx)

    def __len__(self):
        return len(self._idx)


def tabla_de_partes(destino: pathlib.Path, modo: str):
    """Todas las partes de un modo en una tabla (s, d, c, v), con caché en `_<modo>.parquet` que se rehace si cambian
    las partes (nombre y tamaño)."""
    import datetime as dt
    import pandas as pd
    partes = sorted(destino.glob(f"barras_*_{modo}.jsonl.gz"))
    firma = json.dumps([(p.name, p.stat().st_size) for p in partes])
    cache, firma_f = destino / f"_{modo}.parquet", destino / f"_{modo}.firma"
    if cache.exists() and firma_f.exists() and firma_f.read_text() == firma:
        return pd.read_parquet(cache)
    trozos = []
    for p in partes:
        if p.stat().st_size > 20:
            t = pd.read_json(p, lines=True, compression="gzip", dtype={"s": str, "f": str})
            if len(t):
                trozos.append(t)
    if trozos:
        t = pd.concat(trozos, ignore_index=True)
        t["d"] = pd.to_datetime(t["f"]).map(dt.date.toordinal).astype("int32")
        t = t[["s", "d", "c", "v"]]
    else:
        t = pd.DataFrame({"s": pd.Series(dtype=str), "d": pd.Series(dtype="int32"),
                          "c": pd.Series(dtype=float), "v": pd.Series(dtype="int64")})
    t.to_parquet(cache, index=False)
    firma_f.write_text(firma)
    return t


def leer_series(destinos: list, modo: str) -> SeriesCompactas:
    """Las barras de un modo de varias pasadas; si una fecha de un símbolo está en dos, manda la pasada posterior."""
    import pandas as pd
    t = pd.concat([tabla_de_partes(d, modo) for d in destinos], ignore_index=True)
    return SeriesCompactas(t.drop_duplicates(["s", "d"], keep="last"))
