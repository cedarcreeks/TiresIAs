"""Fase 2B: rentabilidades mensuales por CUSIP, sin sesgo de supervivencia (docs/PLAN_FASE2.md, «Precios»).

Lo que mide la sonda del 31-oct y por qué este módulo es así:
  - `asof` de Alpaca empalma empresas (META con asof=2021-06-01: el ETF de Roundhill y después Meta) y mezcla ajustes;
    por eso la entidad se comprueba día a día: el cierre sin ajustar de la consulta por defecto tiene que coincidir con
    el de lo que cotizó con ese símbolo ese día (`asof=-`).
  - un símbolo sin negociación sale relleno con barras de volumen 0 que repiten el último cierre: se descartan.
  - en los spin-offs no acierta ni Alpaca ni Yahoo: el día ex se rehace desde el precio sin ajustar y lo escindido.

Piezas, cada una con sus tests (tests/test_tiresias_precios.py):
  1. `tramos`: con qué símbolo cotizó un CUSIP en cada fecha de una ventana (FTD, recortado con los cambios de nombre).
  2. `serie_diaria`: la rentabilidad diaria de un CUSIP en su ventana y el camino por el que salió.
  3. `mensual` y `salida_pesimista`: lo mensual, y la cota pesimista de la robustez.
  4. `Alpaca`: la descarga (sólo biblioteca estándar, para correr en la máquina que tiene las claves).
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SALTO_MAX = 0.40          # un salto diario mayor sin evento que lo explique descarta la ventana (camino reconstruido)
TOLERANCIA_ENTIDAD = 1e-4  # diferencia relativa admitida entre el cierre por defecto y el de lo que cotizó
CAIDA_PESIMISTA = 0.5     # salida sin fusión con el último cierre por debajo de la mitad del máximo de 12 meses
DIAS_SALIDA = 7           # un valor que deja de cotizar más de 7 días antes del fin de su ventana ha salido de bolsa
CONTRASTE_MAX = 0.01      # mediana de |Δ| entre el precio del FTD y el cierre de Alpaca para dar por buena una traducción

UN_DIA = dt.timedelta(days=1)


# ── 1. los tramos de símbolo ─────────────────────────────────────────────────
def tramos(registros: list, desde: dt.date, hasta: dt.date, cambios: list = (), dias_posterior: int = 90) -> list:
    """[(símbolo, inicio, fin)] de un CUSIP en [desde, hasta], ambos incluidos.

    `registros`: [(fecha, símbolo)] de los FTD de ese CUSIP, ordenados. El primer símbolo es el del registro más
    cercano anterior a `desde` (o el primero posterior dentro de `dias_posterior`); cada registro posterior con otro
    símbolo abre un tramo. `cambios`: [(fecha, viejo, nuevo)] de los corporate actions de ese CUSIP, que dan el día
    exacto del cambio (un FTD llega hasta dos semanas tarde)."""
    previos = [r for r in registros if r[0] <= desde]
    if previos:
        actual = previos[-1][1]
    else:
        posteriores = [r for r in registros if r[0] > desde]
        if not posteriores or (posteriores[0][0] - desde).days > dias_posterior:
            return []
        actual = posteriores[0][1]
    out = [[actual, desde, hasta]]
    for f, s in registros:
        if desde < f <= hasta and s != out[-1][0]:
            out[-1][2] = f - UN_DIA
            out.append([s, f, hasta])
    for f, viejo, nuevo in sorted(cambios):
        for k, t in enumerate(out):
            if t[0] == viejo and t[1] < f <= t[2]:
                if k + 1 < len(out) and out[k + 1][0] == nuevo:
                    out[k + 1][1] = f
                else:
                    out.insert(k + 1, [nuevo, f, t[2]])
                t[2] = f - UN_DIA
                break
    return [tuple(t) for t in out if t[1] <= t[2]]


def forma_con_punto(simbolo: str):
    """El FTD escribe las clases sin punto (BRKB, BFB, LENB, HEIA); Alpaca, con él. No se puede poner a ciegas: BRKL y
    BRKR son otras empresas. Esta es la forma candidata, que sólo vale si cuadra con el precio del FTD."""
    return simbolo[:-1] + "." + simbolo[-1] if len(simbolo) >= 2 and "." not in simbolo else None


def contraste_ftd(registros: list, tal_cual: dict) -> tuple:
    """(comparados, mediana de |Δ|) entre el precio de cada registro FTD [(fecha de liquidación, precio)] —el cierre
    del día anterior, según la SEC— y el cierre sin ajustar de lo que cotizó con el símbolo el día hábil anterior.
    Medido el 31-oct con 27 valores conocidos: mediana y p99, 0,000 %. Sin registros con precio, (0, None)."""
    cierres = _con_volumen(tal_cual)
    fechas = sorted(cierres)
    difs = []
    for f, precio in registros:
        if precio is None or precio != precio or precio <= 0:
            continue
        i = bisect.bisect_left(fechas, f) - 1
        if i >= 0 and (f - fechas[i]).days <= 7:
            difs.append(abs(precio / cierres[fechas[i]] - 1))
    if not difs:
        return 0, None
    difs.sort()
    k = len(difs)
    return k, (difs[k // 2] if k % 2 else (difs[k // 2 - 1] + difs[k // 2]) / 2)


# ── 2. la serie diaria de un CUSIP ───────────────────────────────────────────
def _con_volumen(barras: dict) -> dict:
    """{fecha: cierre} sin las barras de volumen 0 (las de relleno). `barras`: {fecha: (cierre, volumen)}."""
    return {f: c for f, (c, v) in barras.items() if v and v > 0}


def _misma_entidad(por_defecto: dict, tal_cual: dict) -> bool:
    """Cada día que se negoció con el símbolo, la consulta por defecto tiene ese día y el mismo cierre sin ajustar."""
    return bool(tal_cual) and all(f in por_defecto and abs(por_defecto[f] / c - 1) <= TOLERANCIA_ENTIDAD
                                  for f, c in tal_cual.items())


def _rentabilidades(cierres: dict) -> dict:
    f = sorted(cierres)
    return {f[i]: cierres[f[i]] / cierres[f[i - 1]] - 1 for i in range(1, len(f))}


def serie_diaria(tramos_barras: list, acciones: dict, cierres_ajenos: dict, hasta: dt.date) -> tuple:
    """La rentabilidad diaria de un CUSIP en su ventana: ({fecha: r}, camino, {fecha: cierre sin ajustar}).

    `tramos_barras`: por tramo, (símbolo, inicio, fin, todo, sin_ajustar, tal_cual), cada serie {fecha: (cierre,
    volumen)}: `todo` y `sin_ajustar`, de la consulta por defecto (adjustment=all y raw); `tal_cual`, raw con asof=-.
    `acciones`: los corporate actions de ese CUSIP, como los da Alpaca (`cash_dividends`, `forward_splits`,
    `reverse_splits`, `spin_offs`, `cash_mergers`, `stock_mergers`, `stock_and_cash_mergers`). `cierres_ajenos`:
    {(símbolo, fecha): cierre sin ajustar} de lo escindido y de los compradores.

    camino: «alpaca» (la entidad coincide en todos los tramos: el ajuste de Alpaca), «reconstruida» (desde el precio
    sin ajustar y los eventos de ese CUSIP), «descartada» (sin precio, o un salto sin evento) o «sin datos»."""
    crudo, r, alpaca = {}, {}, True
    for _, ini, fin, todo, sin_ajustar, tal_cual in tramos_barras:
        tc = {f: c for f, c in _con_volumen(tal_cual).items() if ini <= f <= fin}
        crudo.update(tc)
        alpaca = alpaca and _misma_entidad(_con_volumen(sin_ajustar), tc)
        if alpaca:
            aj = {f: c for f, c in _con_volumen(todo).items() if f in tc}
            if set(aj) != set(tc):
                alpaca = False
            else:
                for f, x in _rentabilidades(aj).items():
                    r[f] = x
    if len(crudo) < 2:
        return {}, "sin datos", crudo
    fechas = sorted(crudo)
    if alpaca:
        # la unión de dos tramos (un cambio de símbolo): el precio no cambia con el nombre
        for i in range(1, len(fechas)):
            r.setdefault(fechas[i], crudo[fechas[i]] / crudo[fechas[i - 1]] - 1)
        camino = "alpaca"
    else:
        div = {}
        for d in acciones.get("cash_dividends", []):
            f = dt.date.fromisoformat(d["ex_date"])
            div[f] = div.get(f, 0.0) + float(d["rate"])
        factor = {}
        for d in acciones.get("forward_splits", []) + acciones.get("reverse_splits", []):
            f = dt.date.fromisoformat(d["ex_date"])
            factor[f] = factor.get(f, 1.0) * float(d["new_rate"]) / float(d["old_rate"])
        r = {}
        for i in range(1, len(fechas)):
            f, p = fechas[i], fechas[i - 1]
            # eventos entre el cierre anterior y este (incluido este día)
            k = 1.0
            dv = 0.0
            for e, x in factor.items():
                if p < e <= f:
                    k *= x
            for e, x in div.items():
                if p < e <= f:
                    dv += x
            r[f] = (crudo[f] * k + dv) / crudo[p] - 1
        camino = "reconstruida"
    for d in acciones.get("spin_offs", []):
        f = dt.date.fromisoformat(d["ex_date"])
        anterior = [x for x in fechas if x < f]
        nuevo = cierres_ajenos.get((d["new_symbol"], f))
        if f in crudo and anterior and nuevo is not None:
            proporcion = float(d["new_rate"]) / float(d.get("source_rate") or 1)
            r[f] = (crudo[f] + proporcion * nuevo + _dividendo(acciones, f)) / crudo[anterior[-1]] - 1
    # ya corregidas por sus eventos: un salto que sigue ahí no lo explica ninguno (o el evento está mal registrado)
    if camino == "reconstruida" and any(abs(x) > SALTO_MAX for x in r.values()):
        return {}, "descartada", crudo
    final = _valor_de_fusion(acciones, cierres_ajenos)
    if final is not None:
        f, valor = final
        ultimo = fechas[-1]
        if ultimo < f <= hasta:
            r[f] = valor / crudo[ultimo] - 1
    return dict(sorted(r.items())), camino, crudo


def _dividendo(acciones: dict, f: dt.date) -> float:
    return sum(float(d["rate"]) for d in acciones.get("cash_dividends", []) if dt.date.fromisoformat(d["ex_date"]) == f)


def _valor_de_fusion(acciones: dict, cierres_ajenos: dict):
    """(fecha efectiva, lo que recibe una acción) de la fusión registrada, o None."""
    for d in acciones.get("cash_mergers", []):
        return dt.date.fromisoformat(d["effective_date"]), float(d["rate"])
    for clave in ("stock_mergers", "stock_and_cash_mergers"):
        for d in acciones.get(clave, []):
            f = dt.date.fromisoformat(d["effective_date"])
            precio = cierres_ajenos.get((d["acquirer_symbol"], f))
            if precio is None:
                return None
            proporcion = float(d["acquirer_rate"]) / float(d.get("acquiree_rate") or 1)
            return f, proporcion * precio + float(d.get("cash_rate") or 0.0)
    return None


# ── 3. lo mensual ────────────────────────────────────────────────────────────
def fin_de_mes(f: dt.date) -> dt.date:
    siguiente = (f.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return siguiente - UN_DIA


def mensual(r: dict, primer_mes: dt.date | None = None) -> dict:
    """{fin de mes: rentabilidad} compuesta de las diarias de cada mes, desde `primer_mes` (el anterior a la ventana
    sólo trae sus últimos días y no se usa). El de la salida de bolsa es parcial (hasta su último día) y después no hay
    nada: `carteras` reparte su peso entre los demás."""
    out = {}
    for f in sorted(r):
        m = fin_de_mes(f)
        if primer_mes is None or m >= primer_mes:
            out[m] = (1 + out.get(m, 0.0)) * (1 + r[f]) - 1
    return out


def salida_pesimista(r_mensual: dict, crudo: dict, hasta: dt.date, con_fusion: bool) -> dict:
    """La cota pesimista de la robustez: si el valor sale de bolsa sin fusión registrada y su último cierre está por
    debajo de `CAIDA_PESIMISTA` de su máximo de 12 meses, su último mes vale −100 %."""
    if con_fusion or not crudo or not r_mensual:
        return r_mensual
    ultimo = max(crudo)
    if (hasta - ultimo).days <= DIAS_SALIDA:
        return r_mensual
    maximo = max(c for f, c in crudo.items() if (ultimo - f).days <= 365)
    if crudo[ultimo] >= CAIDA_PESIMISTA * maximo:
        return r_mensual
    out = dict(r_mensual)
    out[fin_de_mes(ultimo)] = -1.0
    return out


# ── 4. la descarga ───────────────────────────────────────────────────────────
class Alpaca:
    """Barras diarias y corporate actions, con paginación, pausa entre peticiones y reintentos ante 429 y 5xx.
    `abrir` se cambia en los tests; las claves no se imprimen nunca."""

    BASE = "https://data.alpaca.markets"

    def __init__(self, clave: str, secreto: str, pausa: float = 0.35, reintentos: int = 5, abrir=None, dormir=None):
        self._cab = {"APCA-API-KEY-ID": clave, "APCA-API-SECRET-KEY": secreto}
        self.pausa, self.reintentos = pausa, reintentos
        self._abrir = abrir or (lambda req: urllib.request.urlopen(req, timeout=60).read())
        self._dormir = dormir or time.sleep
        self.peticiones = 0
        self.sin_datos = []     # símbolos que no devolvieron nada ni pedidos solos

    def _get(self, ruta: str, q: dict) -> dict:
        url = self.BASE + ruta + "?" + urllib.parse.urlencode(q)
        for intento in range(self.reintentos + 1):
            self._dormir(self.pausa)
            self.peticiones += 1
            try:
                return json.loads(self._abrir(urllib.request.Request(url, headers=self._cab)))
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or intento == self.reintentos:
                    raise
                self._dormir(min(60.0, 2.0 ** intento))
        raise RuntimeError("inalcanzable")

    def barras(self, simbolos: list, desde: str, hasta: str, ajuste: str, asof: str | None = None) -> dict:
        """{símbolo: {fecha: (cierre, volumen)}} de barras diarias SIP.

        En una petición de varios símbolos, Alpaca los traduce a su empresa de hoy y **quita los repetidos sin
        avisar** (FB y META juntos devuelven sólo META; SQ y XYZ, sólo XYZ; medido el 31-oct): cada símbolo pedido
        que no vuelve se pide solo, y el que siga sin nada queda en `sin_datos`."""
        q = {"symbols": ",".join(simbolos), "timeframe": "1Day", "start": desde, "end": hasta,
             "adjustment": ajuste, "feed": "sip", "limit": 10000}
        if asof:
            q["asof"] = asof
        out = {}
        while True:
            d = self._get("/v2/stocks/bars", q)
            for s, bs in (d.get("bars") or {}).items():
                serie = out.setdefault(s, {})
                for b in bs:
                    serie[dt.date.fromisoformat(b["t"][:10])] = (float(b["c"]), int(b["v"]))
            if not d.get("next_page_token"):
                break
            q["page_token"] = d["next_page_token"]
        if len(simbolos) == 1:
            if not out:
                self.sin_datos.append((simbolos[0], desde, hasta, ajuste, asof))
            return out
        # sólo lo pedido: la clave de un símbolo traducido (META por FB) se queda si también se pidió
        out = {s: x for s, x in out.items() if s in simbolos}
        for s in simbolos:
            if s not in out:
                out.update(self.barras([s], desde, hasta, ajuste, asof))
        return out

    def acciones(self, desde: str, hasta: str, cusips: list = (), simbolos: list = ()) -> dict:
        """{tipo: [registro]} de los corporate actions de esos CUSIP o de esos símbolos (hacen falta las dos
        consultas: ver `acciones_de`)."""
        q = {"start": desde, "end": hasta, "limit": 1000}
        if cusips:
            q["cusips"] = ",".join(cusips)
        if simbolos:
            q["symbols"] = ",".join(simbolos)
        out = {}
        while True:
            d = self._get("/v1/corporate-actions", q)
            for k, v in (d.get("corporate_actions") or {}).items():
                out.setdefault(k, []).extend(v)
            if not d.get("next_page_token"):
                return out
            q["page_token"] = d["next_page_token"]


# Qué campo dice de quién es cada tipo de evento, con qué símbolo y en qué fecha.
_PAPEL = {"spin_offs": ("source_cusip", "source_symbol", "ex_date"),
          "cash_mergers": ("acquiree_cusip", "acquiree_symbol", "effective_date"),
          "stock_mergers": ("acquiree_cusip", "acquiree_symbol", "effective_date"),
          "stock_and_cash_mergers": ("acquiree_cusip", "acquiree_symbol", "effective_date"),
          "name_changes": ("old_cusip", "old_symbol", "process_date")}


def acciones_de(cusip: str, todas: dict, tramos_c: list = ()) -> dict:
    """Los corporate actions de un CUSIP, de la respuesta de varios. Es suyo un evento con su CUSIP en el campo que le
    toca (`source_cusip` en un spin-off, `acquiree_cusip` en una fusión, `old_cusip` en un cambio de nombre), o con el
    símbolo de uno de sus tramos en una fecha de ese tramo: antes de 2020 Alpaca no pone CUSIP (los dividendos de GE de
    2016-2019) y a veces pone el de hoy (el spin-off de WAB de 2019, con el CUSIP de GE de después de 2021). Sin
    duplicados (`id`)."""
    out = {}
    for k, v in todas.items():
        campo_c, campo_s, campo_f = _PAPEL.get(k, ("cusip", "symbol", "ex_date"))
        vistos, sel = set(), []
        for d in v:
            mio = d.get(campo_c) == cusip
            if not mio and d.get(campo_s) and d.get(campo_f):
                f = dt.date.fromisoformat(d[campo_f])
                mio = any(s == d[campo_s] and i <= f <= h for s, i, h in tramos_c)
            if mio and d.get("id", id(d)) not in vistos:
                vistos.add(d.get("id", id(d)))
                sel.append(d)
        out[k] = sel
    return out


# ── 5. el plan de descarga y el montaje ──────────────────────────────────────
def plan(ventanas: dict, registros: dict, cambios: dict) -> tuple:
    """({cusip: tramos}, {símbolo: (desde, hasta)}): qué símbolo pedir y en qué fechas, para todas las ventanas.
    `ventanas`: {cusip: (desde, hasta)}; `registros`: {cusip: [(fecha, símbolo)]} de los FTD; `cambios`: {cusip:
    [(fecha, viejo, nuevo)]} de los corporate actions."""
    por_cusip, rangos = {}, {}
    for c, (d, h) in ventanas.items():
        t = tramos(registros.get(c, []), d, h, cambios.get(c, ()))
        if t:
            por_cusip[c] = t
        for s, i, f in t:
            a, b = rangos.get(s, (i, f))
            rangos[s] = (min(a, i), max(b, f))
    return por_cusip, rangos


def cambios_de_nombre(acciones_c: dict) -> list:
    """[(fecha, viejo, nuevo)] de los cambios de nombre de un CUSIP."""
    return sorted((dt.date.fromisoformat(d["process_date"]), d["old_symbol"], d["new_symbol"])
                  for d in acciones_c.get("name_changes", []))


def con_fusion(acciones_c: dict) -> bool:
    return any(acciones_c.get(k) for k in ("cash_mergers", "stock_mergers", "stock_and_cash_mergers"))


def rentabilidades(por_cusip: dict, series: dict, acciones: dict, cierres_ajenos: dict, ventanas: dict,
                   pesimista: bool = False) -> tuple:
    """({cusip: {fin de mes: r}}, {cusip: camino}). `series`: {"all"|"raw"|"tal_cual": {símbolo: {fecha: (cierre,
    volumen)}}}; `acciones`: {cusip: corporate actions de ese CUSIP}; `ventanas`: {cusip: (desde, hasta)}, con
    `desde` en el mes anterior al primero que se usa."""
    out, caminos = {}, {}
    for c, ts in por_cusip.items():
        desde, hasta = ventanas[c]
        tb = [(s, i, f, series["all"].get(s, {}), series["raw"].get(s, {}), series["tal_cual"].get(s, {}))
              for s, i, f in ts]
        a = acciones.get(c, {})
        r, camino, crudo = serie_diaria(tb, a, cierres_ajenos, hasta)
        caminos[c] = camino
        if not r:
            continue
        # un mes sin cierre del mes anterior sería parcial (Alpaca empieza el 4-ene-2016): el primero, el siguiente
        # al del primer cierre, y nunca antes del que pide la ventana
        primer = max(fin_de_mes(fin_de_mes(desde) + UN_DIA), fin_de_mes(fin_de_mes(min(crudo)) + UN_DIA))
        m = mensual(r, primer_mes=primer)
        out[c] = salida_pesimista(m, crudo, hasta, con_fusion(a)) if pesimista else m
    return out, caminos
