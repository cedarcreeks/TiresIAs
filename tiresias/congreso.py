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


# ── 5. la cartera que copia a los elegidos ───────────────────────────────────
DIAS_TENENCIA = 182
MESES_HISTORIAL, MINIMO_COMPRAS = 24, 5


def centro_tramo(minimo) -> float:
    """El centro del tramo legal de importe (el de «más de 50 M» vale su mínimo)."""
    if minimo is None:
        return float("nan")
    maximo = TRAMOS.get(minimo, minimo)
    return (minimo + maximo) / 2


def posicion(compra: dict, r_diaria: dict, dias: int = DIAS_TENENCIA):
    """La posición de una compra declarada: se entra al cierre del primer día de mercado **posterior** a la
    presentación (no se sabe a qué hora se publica) y se sale `dias` después. Devuelve {"miembro", "presentado",
    "entrada", "peso", "r": {fecha: rentabilidad diaria}, "total"} o None si no hay precio para entrar."""
    import datetime as dt
    fechas = sorted(f for f in r_diaria if f > compra["presentado"])
    if not fechas:
        return None
    entrada = fechas[0]                       # su rentabilidad es la del día de entrada: no se cobra
    fin = entrada + dt.timedelta(days=dias)
    r = {f: x for f, x in r_diaria.items() if entrada < f <= fin}
    total = float(pd_prod(r.values())) - 1 if r else 0.0
    return {"miembro": compra["congresista"], "presentado": compra["presentado"], "entrada": entrada,
            "salida": fin, "peso": centro_tramo(compra.get("importe_min")), "r": r, "total": total}


def pd_prod(xs) -> float:
    p = 1.0
    for x in xs:
        p *= 1 + x
    return p


def fin_trimestre(f):
    import datetime as dt
    mes = 3 * ((f.month - 1) // 3) + 3
    sig = dt.date(f.year + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    return sig - dt.timedelta(days=1)


def historial(posiciones: list, q, meses: int = MESES_HISTORIAL, minimo: int = MINIMO_COMPRAS) -> dict:
    """{miembro: rentabilidad media a 6 meses} con lo que se sabe al cierre del trimestre `q`: sus compras presentadas
    en los `meses` anteriores **cuya tenencia ya acabó** antes de `q` (si no, se miraría al futuro); al menos `minimo`."""
    import datetime as dt
    desde = q - dt.timedelta(days=round(meses * 30.44))
    por = {}
    for p in posiciones:
        if desde < p["presentado"] and p["salida"] <= q:
            por.setdefault(p["miembro"], []).append(p["total"])
    return {m: sum(v) / len(v) for m, v in por.items() if len(v) >= minimo}


def cartera_diaria(posiciones: list, elegidos: dict, ponderar: bool = True):
    """Rentabilidad diaria de copiar: cada compra de un miembro elegido al cierre del trimestre anterior a su
    presentación entra con su peso (centro del tramo, o igual) y vive su tenencia aunque el miembro deje de estarlo.
    `elegidos`: {fin de trimestre: conjunto de miembros}. Un día sin ninguna posición, sin rentabilidad."""
    import pandas as pd
    import datetime as dt
    num, den = {}, {}
    for p in posiciones:
        q = fin_trimestre(p["presentado"])
        # el día 1 del PRIMER mes del trimestre, menos un día (con el del último mes caía en el mismo trimestre y se
        # copiaba con la elección del trimestre en curso: lo cazó su test)
        q_anterior = dt.date(q.year, q.month - 2, 1) - dt.timedelta(days=1)
        if p["miembro"] not in elegidos.get(q_anterior, set()):
            continue
        w = p["peso"] if ponderar and p["peso"] == p["peso"] else 1.0
        for f, x in p["r"].items():
            num[f] = num.get(f, 0.0) + w * x
            den[f] = den.get(f, 0.0) + w
    return pd.Series({f: num[f] / den[f] for f in sorted(num)}, dtype=float)


# ── 6. los precios de las compras ────────────────────────────────────────────
def ventanas_precios(compras: list, fin, dias: int = DIAS_TENENCIA, margen: int = 10) -> dict:
    """{símbolo: (desde, hasta)}: de unos días antes de su primera presentación (el cierre de partida) a su última
    presentación más la tenencia y un margen (la entrada es el día de mercado siguiente), y nunca después de `fin`, el
    último día cerrado: Alpaca da 403 a todo el lote si se piden los últimos 15 min del SIP (pasó con fechas de 2027)."""
    import datetime as dt
    out = {}
    for c in compras:
        a = c["presentado"] - dt.timedelta(days=margen)
        b = c["presentado"] + dt.timedelta(days=dias + margen)
        x, y = out.get(c["ticker"], (a, b))
        out[c["ticker"]] = (min(x, a), min(max(y, b), fin))
    return out


def rentabilidades_diarias(ventanas: dict, series: dict, indice) -> tuple:
    """({símbolo: {fecha: r}}, {símbolo: camino}) con `precios.serie_diaria`, la misma comprobación de entidad que 2B
    (lo que cotizó con ese símbolo en esas fechas frente a la consulta por defecto) y los eventos por símbolo y fecha."""
    from tiresias import precios as P
    out, caminos = {}, {}
    for s, (desde, hasta) in ventanas.items():
        tb = [(s, desde, hasta, series["all"].get(s, {}), series["raw"].get(s, {}), series["tal_cual"].get(s, {}))]
        r, camino, _ = P.serie_diaria(tb, indice.de(s, [(s, desde, hasta)]), {}, hasta)
        caminos[s] = camino
        if r:
            out[s] = r
    return out, caminos


# ── 7. el juicio de 3C ───────────────────────────────────────────────────────
DECIL, REPS = 0.10, 200


def elecciones(posiciones: list, trimestres: list, elegir) -> dict:
    """{fin de trimestre: conjunto elegido} con `elegir(historial) -> conjunto`."""
    return {q: set(elegir(historial(posiciones, q))) for q in trimestres}


def decil_superior(hist: dict) -> set:
    orden = sorted(hist, key=lambda m: hist[m], reverse=True)
    return set(orden[:max(1, round(len(orden) * DECIL))]) if orden else set()


def azar(semilla: int):
    import random
    rng = random.Random(semilla)

    def f(hist):
        miembros = sorted(hist)
        n = max(1, round(len(miembros) * DECIL)) if miembros else 0
        return set(rng.sample(miembros, n)) if n else set()
    return f


def mensual(diaria):
    """Rentabilidad mensual (fin de mes) compuesta de las diarias."""
    import pandas as pd
    s = diaria.copy()
    s.index = pd.to_datetime(s.index)
    return (1 + s).groupby(s.index.to_period("M")).prod().sub(1).to_timestamp("M")


def juicio(posiciones: list, trimestres: list, sp, rf, nanc, reps: int = REPS, ponderar: bool = True) -> dict:
    """Los tres criterios de 3C: frente al S&P 500 (Sharpe +0,10 y CAGR +1 pp en las dos mitades), por encima del p95
    del placebo (congresistas al azar, `reps` veces) y por encima de NANC en el periodo común."""
    from tiresias import gestores as G
    eleg = elecciones(posiciones, trimestres, decil_superior)
    copia = mensual(cartera_diaria(posiciones, eleg, ponderar))
    idx = copia.index.intersection(sp.index).intersection(rf.index)
    c_ex, s_ex = copia.loc[idx] - rf.loc[idx], sp.loc[idx] - rf.loc[idx]
    mitad = idx[len(idx) // 2]

    def gana(a, b):
        ma, mb = G.metricas(a, rf), G.metricas(b, rf)
        return ma["sharpe"] - mb["sharpe"] >= 0.10 and ma["cagr"] - mb["cagr"] >= 0.01
    plac = []
    for s in range(reps):
        m = mensual(cartera_diaria(posiciones, elecciones(posiciones, trimestres, azar(s)), ponderar))
        m = m.loc[m.index.intersection(idx)]
        if len(m) > 12:
            plac.append(G.metricas(m - rf.loc[m.index], rf)["sharpe"])
    sh = G.metricas(c_ex, rf)["sharpe"]
    comun = idx.intersection(nanc.index)
    sh_c, sh_n = (G.metricas(c_ex.loc[comun], rf)["sharpe"], G.metricas(nanc.loc[comun] - rf.loc[comun], rf)["sharpe"]) \
        if len(comun) > 12 else (float("nan"), float("nan"))
    import numpy as np
    crit = {"1_frente_al_sp500_en_las_dos_mitades": gana(c_ex.loc[:mitad - pd_mes()], s_ex.loc[:mitad - pd_mes()])
            and gana(c_ex.loc[mitad:], s_ex.loc[mitad:]),
            "2_sobre_el_placebo_p95": bool(plac) and sh > float(np.percentile(plac, 95)),
            "3_sobre_nanc": bool(sh_c == sh_c and sh_c > sh_n)}
    return {"meses": [str(idx.min().date()), str(idx.max().date()), int(len(idx))],
            "copia": G.metricas(c_ex, rf), "sp500": G.metricas(s_ex, rf),
            "placebo_n": len(plac), "placebo_mediana": float(np.median(plac)) if plac else None,
            "placebo_p95": float(np.percentile(plac, 95)) if plac else None,
            "nanc_comun": {"meses": int(len(comun)), "copia_sharpe": sh_c, "nanc_sharpe": sh_n},
            "elegidos_por_trimestre": [len(eleg[q]) for q in trimestres],
            "criterios": crit, "cumplidos": int(sum(crit.values())), "pasa": all(crit.values())}


def pd_mes():
    import pandas as pd
    return pd.offsets.MonthEnd(1)
