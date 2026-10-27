"""TiresIAs: el veredicto. Cada condición tiene su rama, y la tubería entera sabe decir que sí y que no."""
import math

import numpy as np
import pandas as pd
import pytest

from tiresias import informe as I

BIEN = dict(ic={"ic90": (0.01, 0.05), "por_valor": {"a": 0.1, "b": 0.1, "c": 0.1, "d": -0.1, "e": -0.1}},
            sh={"kronos": 1.5, "comprar y mantener": 1.0, "seguir la semana": 0.5, "media de 200": 0.8},
            mejor="media de 200", p_bh=0.95, p_ing=0.9, p95=1.2)


def _con(**cambios):
    a = {**BIEN, **cambios}
    return I.condiciones(a["ic"], a["sh"], a["mejor"], a["p_bh"], a["p_ing"], a["p95"])


def test_todas_a_la_vez_aporta():
    c = _con()
    assert all(c.values()) and len(c) == 4


@pytest.mark.parametrize("cambio, cual", [
    ({"ic": {**BIEN["ic"], "ic90": (0.0, 0.05)}}, "1"),                       # el límite toca 0: no
    ({"sh": {**BIEN["sh"], "kronos": 0.9}}, "2"),                             # peor que mantener
    ({"sh": {**BIEN["sh"], "media de 200": 1.6}, "mejor": "media de 200"}, "2"),  # peor que la ingenua
    ({"p_bh": 0.899}, "2"),
    ({"p_ing": 0.5}, "2"),
    ({"p95": 1.5}, "3"),                                                      # igual al p95: no lo supera
    ({"ic": {**BIEN["ic"], "por_valor": {"a": 0.1, "b": 0.1, "c": 0.0, "d": -0.1, "e": -0.1}}}, "4"),  # 0 no es > 0
    ({"sh": {**BIEN["sh"], "kronos": math.nan}}, "2"),                        # nan no aprueba
])
def test_cada_condicion_suspende_por_su_lado(cambio, cual):
    c = _con(**cambio)
    malas = [k[0] for k, v in c.items() if not v]
    assert cual in malas


def _sintetico(d, simbolos, H, perfecta, rng):
    for s in simbolos:
        diario = s.startswith("BTC")
        f = pd.date_range("2023-01-02", periods=900) if diario else pd.bdate_range("2023-01-02", periods=900)
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(f))))
        o = np.append(c[0], c[:-1])                                          # abre donde cerró: sin huecos
        v = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c,
                          "volume": 1.0, "adjclose": c}, index=f)
        v.to_csv(d / f"velas_{s}.csv")
        i = [k for k in range(len(f)) if f[k] >= pd.Timestamp("2024-07-01") and k + H < len(f)]
        real = np.array([c[k + H] / c[k] - 1 for k in i])
        prev = real if perfecta else rng.normal(size=len(i))
        pd.DataFrame({"simbolo": s, "fecha": [str(f[k].date()) for k in i], "H": H, "cierre": c[i],
                      "r_prevista": prev, "p_subida": (prev > 0).astype(float), "r_real": real}
                     ).to_csv(d / f"pred_{s}_H{H}.csv", index=False)


@pytest.mark.parametrize("H", [1, 5])
def test_la_tuberia_dice_que_si_con_señal_perfecta_y_que_no_con_ruido(tmp_path, H):
    simbolos = ["a", "b", "BTC-EUR"]
    (tmp_path / "si").mkdir()
    (tmp_path / "no").mkdir()
    _sintetico(tmp_path / "si", simbolos, H, True, np.random.default_rng(1))
    _sintetico(tmp_path / "no", simbolos, H, False, np.random.default_rng(1))
    si = I.horizonte(tmp_path / "si", simbolos, H, placebos=100, reps=200)
    no = I.horizonte(tmp_path / "no", simbolos, H, placebos=100, reps=200)
    assert si["aporta"], si["condiciones"]
    assert not no["aporta"] and not no["condiciones"]["1 RankIC media > 0 con su intervalo del 90 %"]
    assert si["por_valor"]["BTC-EUR"]["coste"] == 0.0149 and si["por_valor"]["a"]["coste"] == 0.0025
