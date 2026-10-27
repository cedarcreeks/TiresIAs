"""TiresIAs: la predicción de t no ve nada posterior a t."""
import numpy as np
import pandas as pd
import pytest

from tiresias import evaluar as E
from tiresias import modelo as M


@pytest.fixture(scope="module")
def km():
    return M.cargar("small", "cpu")


def _df(n=140, semilla=3):
    rng = np.random.default_rng(semilla)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    idx = pd.bdate_range("2024-04-01", periods=n)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6, "adjclose": c}, index=idx)


def test_solo_desde_el_corte_y_con_su_real(km):
    tok, mod = km
    df = _df()
    p = E.predecir(tok, mod, df, "X", H=5, N=4, lote=16)
    assert p["fecha"].min() >= E.DESDE and len(p) > 0
    i = df.index.get_loc(pd.Timestamp(p["fecha"].iloc[0]))
    assert p["r_real"].iloc[0] == pytest.approx(df["close"].iloc[i + 5] / df["close"].iloc[i] - 1)
    assert ((p["p_subida"] >= 0) & (p["p_subida"] <= 1)).all()


def test_cambiar_el_futuro_no_cambia_la_prediccion(km):
    """Precios inventados después de t: ni la predicción de t ni las del mismo lote
    anteriores a t cambian (tampoco a través del azar compartido del lote)."""
    tok, mod = km
    df = _df()
    a = E.predecir(tok, mod, df, "X", H=5, N=4, lote=16)
    corte = a["fecha"].iloc[8]
    otro = df.copy()
    despues = otro.index > pd.Timestamp(corte)
    otro.loc[despues, ["open", "high", "low", "close"]] *= np.linspace(0.5, 2.0, despues.sum())[:, None]
    b = E.predecir(tok, mod, otro, "X", H=5, N=4, lote=16)
    cols = ["r_prevista", "p_subida", "r_p10", "r_p50", "r_p90"]
    hasta = a["fecha"] <= corte
    pd.testing.assert_frame_equal(a.loc[hasta, cols], b.loc[hasta, cols])
    assert not a.loc[~hasta, "r_real"].equals(b.loc[~hasta, "r_real"]), "el montaje: el futuro sí cambió"


def test_muestras_reproduce_la_prediccion_de_su_fecha(km):
    """El ejemplo del informe rehace el lote de su fecha: la media de sus trayectorias es la r_prevista que
    `predecir` guardó. Con otro tamaño de lote (otra semilla y otro azar compartido) ya no lo sería."""
    tok, mod = km
    df = _df()
    p = E.predecir(tok, mod, df, "X", H=5, N=4, lote=16)
    f = p["fecha"].iloc[20]                                   # en el segundo lote
    z = E.muestras(tok, mod, df, "X", 5, f, N=4, lote=16)
    c0 = float(df.loc[f, "close"])        # float de Python, como en `predecir` (con np.float64 cambia el redondeo)
    assert z.shape == (4, 5, 6)
    assert float((z[:, -1, 3] / c0 - 1).mean()) == p.loc[p.fecha == f, "r_prevista"].item()      # exacta
    otro = E.muestras(tok, mod, df, "X", 5, f, N=4, lote=15)
    assert abs(float((otro[:, -1, 3] / c0 - 1).mean()) - p.loc[p.fecha == f, "r_prevista"].item()) > 1e-4


def test_solo_predice_las_fechas_pedidas_y_sin_mirar_el_futuro(km):
    """La rejilla semanal: sólo esas fechas, con su real a H; y la de t no cambia si se inventa el futuro."""
    tok, mod = km
    df = _df()
    rejilla = list(df.index[E.L + 30::5])
    p = E.predecir(tok, mod, df, "X", H=5, N=4, lote=8, solo=rejilla)
    assert set(p["fecha"]) == {str(d.date()) for d in rejilla if df.index.get_loc(d) + 5 < len(df)}
    otro = df.copy()
    corte = pd.Timestamp(p["fecha"].iloc[3])
    otro.loc[otro.index > corte, ["open", "high", "low", "close"]] *= 1.7
    q = E.predecir(tok, mod, otro, "X", H=5, N=4, lote=8, solo=rejilla)
    hasta = p["fecha"] <= str(corte.date())
    pd.testing.assert_frame_equal(p.loc[hasta, ["r_prevista", "p_subida"]], q.loc[hasta, ["r_prevista", "p_subida"]])
