"""TiresIAs: las trayectorias son las de Kronos (su media, lo que da predict_batch)."""
import numpy as np
import pandas as pd
import pytest
import torch

from model import KronosPredictor
from tiresias import modelo as M


@pytest.fixture(scope="module")
def km():
    return M.cargar("small", "cpu")


def _series(n=60, semilla=0):
    rng = np.random.default_rng(semilla)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6})
    return df, pd.Series(pd.bdate_range("2025-01-02", periods=n))


def test_la_media_de_las_trayectorias_es_predict_batch(km):
    tok, mod = km
    L, H, N = 40, 5, 4
    dfs, th, tf = [], [], []
    for s in range(3):
        df, ts = _series(semilla=s)
        dfs.append(df.iloc[:L].reset_index(drop=True))
        th.append(ts.iloc[:L].reset_index(drop=True))
        tf.append(pd.Series(pd.bdate_range(ts.iloc[L], periods=H)))
    z = M.trayectorias(tok, mod, dfs, th, tf, H, N, T=0.6, top_p=0.9, seed=7)
    assert z.shape == (3, N, H, 6)
    torch.manual_seed(7)
    ref = KronosPredictor(mod, tok, device="cpu").predict_batch(dfs, th, tf, pred_len=H, T=0.6, top_p=0.9,
                                                                sample_count=N, verbose=False)
    for i in range(3):
        np.testing.assert_allclose(z[i].mean(axis=0), ref[i][M.COLUMNAS].to_numpy(), rtol=1e-5)
    assert np.std(z[:, :, -1, 3], axis=1).min() > 0, "con N > 1 las trayectorias no son todas iguales"


def test_la_semilla_fija_el_resultado(km):
    tok, mod = km
    df, ts = _series()
    a = M.trayectorias(tok, mod, [df.iloc[:40]], [ts.iloc[:40]], [pd.Series(pd.bdate_range(ts.iloc[40], periods=3))], 3, 5, seed=1)
    b = M.trayectorias(tok, mod, [df.iloc[:40]], [ts.iloc[:40]], [pd.Series(pd.bdate_range(ts.iloc[40], periods=3))], 3, 5, seed=1)
    c = M.trayectorias(tok, mod, [df.iloc[:40]], [ts.iloc[:40]], [pd.Series(pd.bdate_range(ts.iloc[40], periods=3))], 3, 5, seed=2)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_semilla_estable():
    assert M.semilla("IDR.MC", "2025-01-02", 5) == M.semilla("IDR.MC", "2025-01-02", 5) != M.semilla("ACS.MC", "2025-01-02", 5)
