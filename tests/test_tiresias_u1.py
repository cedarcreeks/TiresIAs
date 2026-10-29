"""TiresIAs: U1. Sesiones sin solape, rentabilidad de apertura a apertura y la cuenta por sesión, con casos sabidos."""
import json

import numpy as np
import pandas as pd

from tiresias import u1 as U1

CAL = pd.bdate_range("2024-07-01", periods=40)


def test_sin_solape_toma_cada_una_a_5_sesiones_o_más():
    f = [CAL[i].strftime("%Y-%m-%d") for i in (0, 2, 4, 5, 9, 10, 16)]
    assert U1.sin_solape(f, CAL) == [f[0], f[3], f[5], f[6]]            # 0, 5, 10, 16


def test_la_rejilla_sólo_deja_las_de_5_en_5():
    f = [CAL[i].strftime("%Y-%m-%d") for i in (0, 2, 5, 9, 10, 16)]
    assert U1.rejilla(f, CAL, "2024-07-01") == [f[0], f[2], f[4]]       # 0, 5, 10


def _velas(tmp_path, s, aperturas):
    c = np.asarray(aperturas, dtype=float)
    pd.DataFrame({"open": c, "high": c, "low": c, "close": c * 2, "volume": 1.0, "adjclose": c},
                 index=CAL[:len(c)]).to_csv(tmp_path / f"velas_{s}.csv")


def test_la_rentabilidad_va_de_la_apertura_de_entrada_a_la_de_5_sesiones_después(tmp_path):
    _velas(tmp_path, "X", 100 + np.arange(20))                            # apertura ajustada = open × 0,5
    s = pd.DataFrame({"ticker": ["X", "X"], "fecha_entrada": [CAL[3].strftime("%Y-%m-%d"), CAL[17].strftime("%Y-%m-%d")]})
    r = U1.rentabilidades(tmp_path, s)
    assert abs(r[0] - (108 / 103 - 1)) < 1e-12                          # 3 → 8
    assert 1 not in r.index                                                # sin 5 sesiones por delante, fuera


def test_por_sesión_con_una_puntuación_perfecta():
    g = pd.DataFrame({"fecha": "2024-07-01", "puntuacion": [5, 4, 3, 2, 1, 0.0], "r": [0.06, 0.05, 0.04, 0.03, 0.02, 0.01]})
    ps = U1.por_sesion(g, ["2024-07-01"])
    assert abs(ps["rankic"].iloc[0] - 1) < 1e-12
    assert abs(ps["exceso_mitad"].iloc[0] - (0.05 - 0.035)) < 1e-12        # los 3 de arriba frente a los 6


def test_evaluar_de_principio_a_fin(tmp_path):
    rng = np.random.default_rng(0)
    filas, punt = [], []
    _velas(tmp_path, "SPY", 100 + np.arange(40))
    for j in range(8):
        ap = 100 * np.cumprod(1 + rng.normal(0, 0.02, 40))
        _velas(tmp_path, f"V{j}", ap)
        for i in (0, 1, 6, 12, 20):
            filas.append({"fecha": CAL[i].strftime("%Y-%m-%d"), "fecha_entrada": CAL[i + 1].strftime("%Y-%m-%d"),
                          "ticker": f"V{j}"})
            punt.append({"ticker": f"V{j}", "fecha": CAL[i].strftime("%Y-%m-%d"),
                         "puntuacion": ap[i + 6] / ap[i + 1]})             # la que acierta: la propia rentabilidad
    pd.DataFrame(filas).to_csv(tmp_path / "senales.csv", index=False)
    pd.DataFrame(punt).to_csv(tmp_path / "u1_puntuaciones.csv", index=False)
    (tmp_path / "senales.json").write_text(json.dumps({"desde": "2024-07-01"}))
    r = U1.evaluar(tmp_path)
    assert r["principal"]["n"] == 4                                        # 0, 6, 12, 20 (la 1 solapa con la 0)
    assert abs(r["principal"]["media"] - 1) < 1e-12 and r["principal"]["p_exceso_positivo"] == 1.0
    assert r["rejilla"]["n"] == 2                                          # 0 y 20
