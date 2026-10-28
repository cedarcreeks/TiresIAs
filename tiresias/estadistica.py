# -*- coding: utf-8 -*-
"""La t de Student exacta (beta incompleta regularizada) y la corrección de Holm, sin scipy.

Copiado de thalospi `ops/lab/estadistica.py`, validado allí contra tablas publicadas y aquí otra vez
(tests/test_tiresias_estadistica.py). Con pocas unidades la normal infravalora la cola: declararía significativo lo que no
lo es.
"""
from __future__ import annotations

import math


def _betacf(a: float, b: float, x: float) -> float:
    """Fracción continua de la beta incompleta (Lentz modificado).

    Numerical Recipes §6.4. Converge en ~10 iteraciones para los rangos de
    aquí; el tope de 300 es sólo para no colgarse nunca.
    """
    TINY, EPS = 1e-30, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, 301):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            return h
    raise RuntimeError("betacf no converge")


def beta_incompleta(a: float, b: float, x: float) -> float:
    """I_x(a,b), la beta incompleta regularizada."""
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"x fuera de [0,1]: {x}")
    if x in (0.0, 1.0):
        return x
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def p_t(t: float, gl: int, cola: str = "derecha") -> float:
    """p-valor de una t de Student con `gl` grados de libertad.

    `cola` se declara EN EL PRE-REGISTRO, no después de ver el signo. Elegir
    la cola al ver el resultado duplica la tasa de falsos positivos sin que se
    note en el p publicado.
    """
    if gl < 1:
        raise ValueError(f"grados de libertad inválidos: {gl}")
    # P(T > t) = I_x(gl/2, 1/2)/2 con x = gl/(gl+t²), para t > 0.
    x = gl / (gl + t * t)
    cola_sup = 0.5 * beta_incompleta(gl / 2.0, 0.5, x)
    if t < 0:
        cola_sup = 1.0 - cola_sup
    if cola == "derecha":
        return cola_sup
    if cola == "izquierda":
        return 1.0 - cola_sup
    if cola == "dos":
        return min(1.0, 2.0 * min(cola_sup, 1.0 - cola_sup))
    raise ValueError(f"cola desconocida: {cola}")


def holm(ps: dict, alfa: float = 0.05) -> dict:
    """{nombre: pasa}. Se ordenan los p de menor a mayor; el k-ésimo (desde 0) pasa si p ≤ alfa/(m − k) y han pasado
    todos los anteriores. Un NaN no pasa nunca."""
    orden = sorted(ps, key=lambda k: (math.isnan(ps[k]), ps[k]))
    out, sigue = {}, True
    for k, nombre in enumerate(orden):
        p = ps[nombre]
        sigue = sigue and not math.isnan(p) and p <= alfa / (len(ps) - k)
        out[nombre] = sigue
    return out
