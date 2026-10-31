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


# ── 3. las operaciones de una declaración ────────────────────────────────────
import re  # noqa: E402

# Las de 2016 traen las mayúsculas rotas por la fuente del PDF («(BaX)», «s» por S) y días de una cifra («09/7/2016»)
_FECHAS = re.compile(r"\s([PSE]|S \(partial\))\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+(.*)$", re.I)
_TICKER = re.compile(r"\(([A-Za-z][A-Za-z0-9.\-]{0,6})\)")
_CLASE = re.compile(r"\[([A-Z]{2})\]")
_IMPORTE = re.compile(r"\$([\d,]+)")
# los tramos legales de importe: el mínimo de cada tramo y su máximo
TRAMOS = {1001: 15000, 15001: 50000, 50001: 100000, 100001: 250000, 250001: 500000, 500001: 1000000,
          1000001: 5000000, 5000001: 25000000, 25000001: 50000000, 50000001: 50000001}


def operaciones(texto: str) -> list:
    """Las operaciones de una PTR electrónica (salida de `pdftotext -layout`): una por cada línea con su tipo y sus dos
    fechas (operación y notificación), que es lo único que no se parte. El símbolo es el último «(XXX)» de esa línea o
    de las dos anteriores; la clase de activo («[ST]» acciones), de esa línea o de las dos siguientes; el importe, el
    tramo legal que empieza en el primer «$» tras las fechas. Devuelve [{"ticker", "tipo", "fecha_operacion",
    "fecha_notificacion", "importe_min", "importe_max", "clase"}]; sin ticker, ticker None."""
    lineas = texto.splitlines()
    filas = [i for i, linea in enumerate(lineas) if _FECHAS.search(linea)]
    out = []
    for n, i in enumerate(filas):
        linea = lineas[i]
        m = _FECHAS.search(linea)
        tipo, f_op, f_not, resto = m.groups()
        antes = linea[:m.start()]
        # sin pasar a la operación vecina: un activo sin símbolo heredaba el de la anterior (lo cazó su test)
        previa = filas[n - 1] if n else -1
        siguiente = filas[n + 1] if n + 1 < len(filas) else len(lineas)
        arriba = [lineas[k] for k in (i - 1, i - 2) if k > previa]
        abajo = [lineas[k] for k in (i + 1, i + 2) if k < siguiente]
        def tickers(x):
            return [s.upper() for s in _TICKER.findall(x)]
        # en su línea, o en las de arriba (el nombre partido), o en las de abajo (el símbolo partido: «(FOXa)»)
        tick = tickers(antes) or [s for x in arriba for s in tickers(x)][:1] or [s for x in abajo for s in tickers(x)][:1]
        clase = _CLASE.findall(linea) or [c for x in abajo for c in _CLASE.findall(x)][:1]
        imp = _IMPORTE.findall(resto)
        minimo = int(imp[0].replace(",", "")) if imp else None
        out.append({"ticker": tick[-1] if tick else None, "tipo": tipo[0].upper(),
                    "fecha_operacion": f_op, "fecha_notificacion": f_not, "importe_min": minimo,
                    "importe_max": TRAMOS.get(minimo), "clase": clase[0] if clase else None})
    return out


# ── 4. de los PDF a la tabla de compras ──────────────────────────────────────
def texto_pdf(ruta: pathlib.Path) -> str:
    """El texto de un PDF con `pdftotext -layout` (de Poppler); cadena vacía si no tiene texto (papel escaneado)."""
    import shutil
    import subprocess
    exe = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    return subprocess.run([exe, "-layout", str(ruta), "-"], capture_output=True, text=True).stdout


def extraer(ptrs: list, carpeta: pathlib.Path, leer=texto_pdf) -> tuple:
    """(operaciones, informe): una fila por operación con el congresista y la **fecha de presentación** del índice, que
    es cuando se pudo ver; el informe cuenta declaraciones con texto, sin texto (papel) y sin PDF."""
    import datetime as dt
    filas, informe = [], {"con_texto": 0, "sin_texto": 0, "sin_pdf": 0}
    for p in ptrs:
        f = carpeta / p["anio"] / f"{p['docid']}.pdf"
        if not f.exists():
            informe["sin_pdf"] += 1
            continue
        txt = leer(f)
        if len(txt.strip()) < 50:
            informe["sin_texto"] += 1
            continue
        informe["con_texto"] += 1
        presentado = dt.datetime.strptime(p["presentado"], "%m/%d/%Y").date()
        for o in operaciones(txt):
            filas.append({"congresista": f"{p['apellido']}, {p['nombre']} ({p['distrito']})", "docid": p["docid"],
                          "presentado": presentado, **o})
    return filas, informe


def compras(filas: list) -> list:
    """Las que se copian (PLAN_FASE3, 3C): compras de acciones con símbolo; sin clase (formato antiguo) o con «ST»."""
    return [f for f in filas if f["tipo"] == "P" and f["ticker"] and f["clase"] in (None, "ST")]
