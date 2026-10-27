"""TiresIAs: las métricas de los criterios."""
import numpy as np
import pandas as pd
import pytest

from tiresias import metricas as X


def test_spearman_con_empates():
    a, b = [1, 2, 2, 3], [1, 3, 2, 4]
    ra, rb = np.array([1, 2.5, 2.5, 4]), np.array([1, 3, 2, 4])
    assert X.spearman(a, b) == pytest.approx(np.corrcoef(ra, rb)[0, 1])


def _velas(n=30):
    idx = pd.bdate_range("2025-01-01", periods=n)
    c = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({"open": c - 0.5, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0, "adjclose": c}, index=idx)


def test_siempre_dentro_sin_coste_es_comprar_y_mantener():
    v = _velas()
    dec = pd.Series(True, index=v.index[:-1])
    curva = X.estrategia(v, dec, 1, 0.0)
    ap = X.aperturas_ajustadas(v)
    assert curva.index[0] == v.index[1] and curva.index[-1] == v.index[-1]     # la fecha es la de la apertura
    assert curva.iloc[-1] == pytest.approx(ap.iloc[-1] / ap.iloc[1])


def test_la_señal_de_t_no_cobra_el_salto_hasta_la_apertura():
    v = _velas()
    v.loc[v.index[11], "open"] = 500.0                  # la apertura de t+1 salta (y después vuelve)
    dec = pd.Series([True], index=[v.index[10]])        # dentro tras el cierre de t
    curva = X.estrategia(v, dec, 1, 0.0)
    assert curva.index[0] == v.index[11] and curva.iloc[0] == 1.0      # en la apertura de t+1, aún nada
    r = curva.iloc[1] - 1.0                             # de la apertura de t+1 a la de t+2
    assert r == pytest.approx(v["open"].iloc[12] / 500.0 - 1.0)


def test_una_ida_y_vuelta_cuesta_dos_veces():
    v = _velas()
    v["open"] = 100.0
    dec = pd.Series([True, False], index=[v.index[3], v.index[4]])
    curva = X.estrategia(v, dec, 1, 0.01)
    assert curva.iloc[-1] == pytest.approx(0.99 * 0.99)


def test_cartera_a_partes_iguales():
    i = pd.bdate_range("2025-01-01", periods=3)
    c = X.cartera({"a": pd.Series([1.0, 2.0, 2.0], index=i), "b": pd.Series([2.0, 2.0, 4.0], index=i)})
    assert list(c) == [1.0, 1.5, 2.0]


def test_decisiones_cada_paso_y_umbral_estricto():
    p = pd.DataFrame({"fecha": [f"2025-01-0{d}" for d in range(1, 8)], "p_subida": [0.5, 0.6, 0.7, 0.4, 0.9, 0.5, 0.6]})
    d = X.decisiones_kronos(p, 3)
    assert list(d.index.strftime("%d")) == ["01", "04", "07"] and list(d) == [False, False, True]


def test_reglas_ingenuas():
    v = _velas(260)
    f = v.index[-3:]
    assert X.decisiones_momento(v, f).all() and X.decisiones_media(v, f).all()
    v2 = v.iloc[::-1].copy()
    v2.index = v.index
    assert not X.decisiones_momento(v2, f).any() and not X.decisiones_media(v2, f).any()


def test_bloques_reproducibles():
    a, b = X.bloques(50, 4.0, 3, 1), X.bloques(50, 4.0, 3, 1)
    assert a.shape == (3, 50) and np.array_equal(a, b) and a.max() < 50


def _preds(fechas, rng):
    r = rng.normal(size=len(fechas))
    return pd.DataFrame({"fecha": [str(d.date()) for d in fechas], "r_prevista": r + rng.normal(size=len(fechas)),
                         "r_real": r})


def test_ic_remuestreo_conjunto_por_semanas():
    """Dos valores con las mismas filas tienen la MISMA RankIC en cada réplica: se remuestrean las mismas semanas.
    Un remuestreo por valor (independiente) las daría distintas."""
    rng = np.random.default_rng(3)
    p = _preds(pd.bdate_range("2025-01-01", periods=200), rng)
    m = X.ic_remuestreado({"a": p, "b": p.copy()}, 50, 7)
    assert m.shape == (50, 2) and np.allclose(m[:, 0], m[:, 1]) and m[:, 0].std() > 0


def test_ic_remuestreo_con_calendarios_distintos():
    """Un valor que cotiza a diario y otro en días hábiles: cada réplica toma de los dos las mismas semanas."""
    rng = np.random.default_rng(4)
    pa = _preds(pd.bdate_range("2025-01-06", periods=100), rng)
    pb = _preds(pd.date_range("2025-01-06", periods=140), rng)
    m = X.ic_remuestreado({"a": pa, "b": pb}, 20, 1)
    assert m.shape == (20, 2) and np.isfinite(m).all()


def test_rankic_media_aprueba_lo_bueno_y_no_lo_aleatorio():
    rng = np.random.default_rng(5)
    f = pd.bdate_range("2024-07-01", periods=300)
    bueno = {s: _preds(f, rng) for s in "abc"}
    malo = {s: _preds(f, rng).assign(r_prevista=rng.normal(size=len(f))) for s in "abc"}
    assert X.rankic_media(bueno, 1, reps=200)["ic90"][0] > 0
    lo, hi = X.rankic_media(malo, 1, reps=200)["ic90"]
    assert lo < 0 < hi


def test_wilson_contra_tabla():
    lo, hi = X.wilson(5, 10, z=1.96)                    # valor publicado del intervalo de Wilson del 95 % para 5/10
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)


def _p(prev, real, ps, p10=None, p90=None):
    d = pd.DataFrame({"r_prevista": prev, "r_real": real, "p_subida": ps})
    d["r_p10"] = d["r_prevista"] - 0.01 if p10 is None else p10
    d["r_p90"] = d["r_prevista"] + 0.01 if p90 is None else p90
    return d


def test_acierto_separa_lo_que_dice():
    p = _p([0.0] * 6, [0.01, 0.02, -0.01, 0.01, -0.02, -0.03], [0.9, 0.6, 0.7, 0.2, 0.5, 0.1])
    a = X.acierto(p)                                     # dice sube (>0,5): 3, suben 2 · dice baja (0,5 incluido): 3, sube 1
    assert (a["n_dice_sube"], a["n_dice_baja"]) == (3, 3)
    assert a["sube_si_dice_sube"] == pytest.approx(2 / 3) and a["sube_si_dice_baja"] == pytest.approx(1 / 3)
    assert a["base"] == pytest.approx(0.5)


def test_cobertura_con_bordes():
    p = _p([0.0, 0.0, 0.0, 0.0], [0.01, -0.01, 0.0101, 0.0], [0.5] * 4)
    assert X.cobertura(p) == pytest.approx(3 / 4)


def test_mae_relativo_perfecto_y_nulo():
    real = [0.01, -0.02, 0.03]
    assert X.mae_relativo(_p(real, real, [0.5] * 3)) == 0.0
    assert X.mae_relativo(_p([0.0] * 3, real, [0.5] * 3)) == pytest.approx(1.0)


def test_calibracion_por_probabilidad():
    p = _p([0.0] * 5, [0.01, -0.01, 0.02, 0.01, -0.01], [0.2, 0.2, 0.8, 0.8, 0.8])
    c = X.calibracion(p)
    assert list(c.index) == [0.2, 0.8] and list(c["n"]) == [2, 3] and list(c["k"]) == [1, 2]
    assert (c["lo"] <= c["frecuencia"]).all() and (c["frecuencia"] <= c["hi"]).all()
