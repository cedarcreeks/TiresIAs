"""TiresIAs: U4. El simulador de TopkDropout con casos que saben la respuesta."""
import numpy as np

from tiresias import u4 as U


def _precios(T=40, J=60, semilla=0, deriva=None):
    rng = np.random.default_rng(semilla)
    r = rng.normal(0, 0.01, (T, J)) + (0 if deriva is None else deriva)
    c = 100 * np.cumprod(1 + r, axis=0)
    return c, c.copy()                                   # apertura = cierre: sin huecos


def test_sin_cambio_de_senal_no_hay_rotacion_tras_comprar():
    c, a = _precios()
    S = np.tile(np.arange(60, dtype=float), (40, 1))      # siempre el mismo orden
    r = U.topk_dropout(S, a, c, k=10, n_drop=2, c_compra=0, c_venta=0)
    assert abs(r["rotacion_anual"] * 40 / 252 - 0.95) < 1e-9     # sólo la compra inicial del 95 % del efectivo


def test_la_permanencia_impide_vender_antes_de_5_sesiones():
    c, a = _precios(T=8, J=12)
    S = np.zeros((8, 12))
    S[0, :] = np.arange(12)                               # el día 0 elige los 3 mejores: 9, 10, 11
    S[1:, :] = -np.arange(12)                             # desde el día 1 son los peores: querría venderlos ya
    r1 = U.topk_dropout(S, a, c, k=3, n_drop=3, permanencia=5, c_compra=0, c_venta=0)
    r0 = U.topk_dropout(S, a, c, k=3, n_drop=3, permanencia=1, c_compra=0, c_venta=0)
    assert r1["rotacion_anual"] < r0["rotacion_anual"]    # con permanencia, menos ventas en esos días


def test_cobra_la_compra():
    c, a = _precios(T=3, J=5)
    c[:], a[:] = 100.0, 100.0
    S = np.tile(np.arange(5, dtype=float), (3, 1))
    r = U.topk_dropout(S, a, c, k=5, n_drop=1, riesgo=1.0, c_compra=0.01, c_venta=0)
    assert abs(r["valor"][-1] - 0.99) < 1e-12


def test_puntuacion_perfecta_gana_a_todos():
    c, a = _precios(T=120, J=80, semilla=1)
    S = np.full_like(c, np.nan)
    S[:-2] = a[2:] / a[1:-1] - 1                           # la señal de t ve la apertura t+1 → t+2: la que cobra
    r = U.topk_dropout(S, a, c, k=10, n_drop=10, permanencia=1)
    todos = np.prod(1 + np.nanmean(c[1:] / c[:-1] - 1, axis=1))
    assert r["valor"][-1] > 1.5 * todos


def test_un_cierre_que_falta_no_hunde_la_cartera():
    c, a = _precios(T=10, J=6)
    S = np.tile(np.arange(6, dtype=float), (10, 1))
    base = U.topk_dropout(S, a, c, k=3, n_drop=1)["valor"]
    c2 = c.copy()
    c2[5, 5] = np.nan                                     # el mejor, en cartera, sin cierre el día 5
    hueco = U.topk_dropout(S, a, c2, k=3, n_drop=1)["valor"]
    assert hueco[5] > 0.9 * base[5]


# ── la segunda implementación (verificar_u4) ─────────────────────────────
def _carpeta(tmp_path, T=90, J=110, semilla=3, cada=1):
    """Velas y puntuaciones sintéticas con el formato de los ficheros reales: un SPY de calendario y J valores, algunos
    con huecos (sin apertura) y uno que empieza a cotizar a mitad del periodo."""
    import json

    import pandas as pd
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range("2024-06-03", periods=T)
    simbolos = [f"V{j:03d}" for j in range(J)]
    (tmp_path / "simbolos.json").write_text(json.dumps({"simbolos": ["SPY"] + simbolos}), encoding="utf-8")
    pred = tmp_path / "pred"
    pred.mkdir()
    for s in ["SPY"] + simbolos:
        c = 100 * np.cumprod(1 + rng.normal(0, 0.015, T))
        v = pd.DataFrame({"open": c * (1 + rng.normal(0, 0.003, T)), "high": c * 1.01, "low": c * 0.99, "close": c,
                          "volume": 1e6, "adjclose": c * 0.97}, index=fechas)
        if s == "V005":
            v = v.iloc[40:]                                   # empieza a cotizar a mitad del periodo
        if s == "V007":
            v.loc[v.index[50:53], "open"] = np.nan            # tres días sin apertura
        v.to_csv(tmp_path / f"velas_{s}.csv")
        if s != "SPY":
            p = v.loc[v.index >= U.DESDE].iloc[::cada]
            pd.DataFrame({"fecha": p.index.strftime("%Y-%m-%d"), "puntuacion": rng.normal(0, 1, len(p)),
                          "r_prevista": 0.0}).to_csv(pred / f"pred_{s}.csv", index=False)
    return tmp_path, pred


def test_la_segunda_implementación_coincide_con_u4(tmp_path):
    from tiresias import verificar_u4 as V
    for cada in (1, 10):                                      # el reentrenado (cada sesión) y el original (cada 10)
        (tmp_path / f"c{cada}").mkdir()
        d, pred = _carpeta(tmp_path / f"c{cada}", cada=cada)
        filas = V.comparar(U.evaluar(d, pred, placebos=2), V.verificar(d, pred))
        assert [f[0] for f in filas if not f[3] <= 1e-9] == [], filas


def test_la_segunda_implementación_ve_una_señal_desfasada(tmp_path, monkeypatch):
    """Control negativo: si la cartera de u4 operase con la señal del mismo día (mira el futuro), no coincidirían."""
    from tiresias import verificar_u4 as V
    d, pred = _carpeta(tmp_path)
    original = U.topk_dropout
    monkeypatch.setattr(U, "topk_dropout", lambda S, A, C, **kw: original(np.vstack([S[1:], S[-1:]]), A, C, **kw))
    filas = V.comparar(U.evaluar(d, pred, placebos=2), V.verificar(d, pred))
    assert {"Sharpe cartera", "CAGR cartera"} <= {f[0] for f in filas if f[3] > 1e-9}


def test_la_métrica_del_artículo_es_por_predicción_y_canal():
    real = np.cumsum(np.random.default_rng(0).normal(0, 1, (10, 4)), axis=0) + 100
    assert np.allclose(U.ic_camino(real * 2 + 5, real), (1.0, 1.0), atol=1e-12)   # un camino proporcional acierta
    ic, ric = U.ic_camino(-real, real)
    assert abs(ic + 1) < 1e-12 and abs(ric + 1) < 1e-12
    plano = real.copy()
    plano[:, 0] = 100.0                                                   # un canal previsto sin movimiento no cuenta
    ic, _ = U.ic_camino(plano, real)
    assert abs(ic - 1.0) < 1e-12
