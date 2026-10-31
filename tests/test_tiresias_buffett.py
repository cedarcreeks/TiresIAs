"""Fase 2A: los lectores (French, AQR), las rentabilidades mensuales, la regresión y el veredicto del control."""
import copy
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from tiresias import buffett as B

FRENCH = """This file was created by CMPT_ME_BEME_RETS using the 202609 CRSP database.
The 1-month TBill return is from Ibbotson and Associates, Inc.

,Mkt-RF,SMB,HML,RF
192607,    2.96,   -2.56,   -2.43,    0.22
192608,    2.64,   -1.17,    3.82,    0.25

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
  1927,   29.47,   -2.46,   -3.75,    3.12
"""


def test_french_lee_solo_la_tabla_mensual_en_tanto_por_uno():
    df = B.leer_french(FRENCH)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RF"] and len(df) == 2
    assert df.index[0] == pd.Timestamp("1926-07-31") and df.loc["1926-08-31", "HML"] == pytest.approx(0.0382)


def test_french_sin_filas_falla():
    with pytest.raises(ValueError, match="no hay filas"):
        B.leer_french(",Mom\n\n Annual\n")


def test_aqr_lee_la_columna_usa_a_fin_de_mes(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BAB Factors"
    ws.append(["AQR — cabecera"])
    ws.append([None, "EQUITIES"])
    ws.append(["DATE", "AUS", "USA"])
    ws.append(["01/31/1990", 0.5, 0.01])
    ws.append([dt.datetime(1990, 2, 28), None, -0.02])
    ws.append(["03/30/1990", 0.1, None])        # sin dato de EE. UU.: no entra
    ws.append(["", None, None])               # el final de la tabla, en blanco (así acaban los de AQR)
    ws.append(["04/30/1990", 0.1, 0.03])      # lo de después no entra
    f = tmp_path / "x.xlsx"
    wb.save(f)
    s = B.leer_aqr(f, "BAB Factors")
    assert list(s.index) == [pd.Timestamp("1990-01-31"), pd.Timestamp("1990-02-28")]
    assert list(s) == [0.01, -0.02]


def test_mensual_usa_el_ultimo_cierre_del_mes_y_quita_el_primero():
    idx = pd.to_datetime(["1980-03-17", "1980-03-31", "1980-04-15", "1980-04-30", "1980-05-30"])
    r = B.mensual(pd.Series([100.0, 110.0, 99.0, 121.0, 133.1], index=idx))
    assert list(r.index) == [pd.Timestamp("1980-04-30"), pd.Timestamp("1980-05-31")]
    assert list(r) == pytest.approx([0.10, 0.10])


def test_ols_recupera_los_coeficientes_y_sus_t():
    rng = np.random.default_rng(7)
    X = pd.DataFrame(rng.normal(0, 0.04, (600, 2)), columns=["a", "b"])
    y = pd.Series(0.002 + 0.5 * X["a"] - 0.2 * X["b"] + rng.normal(0, 0.01, 600))
    r = B.ols(y, X)
    assert r["coef"]["alfa"] == pytest.approx(0.002, abs=0.001)
    assert r["coef"]["a"] == pytest.approx(0.5, abs=0.03) and r["coef"]["b"] == pytest.approx(-0.2, abs=0.03)
    # t de la pendiente, a mano: b / (s / (sd(x) * sqrt(n)))
    resid = y - (r["coef"]["alfa"] + r["coef"]["a"] * X["a"] + r["coef"]["b"] * X["b"])
    s = np.sqrt((resid ** 2).sum() / (600 - 3))
    assert r["t"]["a"] == pytest.approx(r["coef"]["a"] / (s / (X["a"].std(ddof=0) * np.sqrt(600))), rel=0.05)
    r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
    assert r["n"] == 600 and r["r2_ajustado"] == pytest.approx(1 - (1 - r2) * 599 / 597)


def test_tabla4_anualiza_el_alfa():
    rng = np.random.default_rng(3)
    f = pd.DataFrame(rng.normal(0, 0.04, (300, 6)), columns=["MKT", "SMB", "HML", "UMD", "BAB", "QMJ"])
    f["EXCESO"] = 0.005 + f["MKT"] + rng.normal(0, 0.01, 300)
    t4 = B.tabla4(f)
    assert set(t4) == {"columna 1", "columna 2", "columna 3"}
    assert t4["columna 3"]["coef"]["alfa"] == pytest.approx(0.06, abs=0.02)        # 0,005 × 12
    assert set(t4["columna 2"]["coef"]) == {"alfa", "MKT", "SMB", "HML", "UMD", "BAB"}


def _como_publicado():
    return {col: {"coef": {k: v[0] for k, v in p.items()}, "t": {k: v[1] for k, v in p.items()}}
            for col, p in B.PUBLICADO.items()}


def test_veredicto_pasa_con_las_cifras_publicadas():
    v = B.veredicto(_como_publicado())
    assert v["pasa"] and v["cumplidos"] == 3


@pytest.mark.parametrize("romper,criterio", [
    (lambda t: t["columna 3"]["coef"].update(BAB=0.29 + 0.16), "1_cargas_a_015"),
    (lambda t: t["columna 3"]["coef"].update(MKT=0.95 - 0.151), "1_cargas_a_015"),
    (lambda t: t["columna 3"]["t"].update(QMJ=1.99), "2_bab_y_qmj_positivos_t2"),
    (lambda t: t["columna 3"]["coef"].update(BAB=-0.01), "2_bab_y_qmj_positivos_t2"),
    (lambda t: t["columna 1"]["t"].update(alfa=1.99), "3_alfa_4f_t2_y_6f_no"),
    (lambda t: t["columna 3"]["t"].update(alfa=2.0), "3_alfa_4f_t2_y_6f_no"),
])
def test_cada_criterio_tumba_el_control(romper, criterio):
    t = copy.deepcopy(_como_publicado())
    romper(t)
    v = B.veredicto(t)
    assert not v["pasa"] and not v["criterios"][criterio], v
