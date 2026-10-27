"""TiresIAs: las preguntas exploratorias (volatilidad y minería de reglas)."""
import numpy as np
import pandas as pd
import pytest

from tiresias import estudios as S


def test_parcial_a_mano():
    assert S.parcial(0.5, 0.5, 0.5) == pytest.approx(0.25 / 0.75)
    assert S.parcial(0.3, 0.0, 0.0) == pytest.approx(0.3)                 # sin relación con z, no cambia


def test_parkinson_constante():
    idx = pd.bdate_range("2025-01-01", periods=30)
    v = pd.DataFrame({"high": np.exp(0.1), "low": 1.0}, index=idx)
    assert S.parkinson(v).iloc[-1] == pytest.approx(np.sqrt(0.01 / (4 * np.log(2))))
    assert np.isnan(S.parkinson(v).iloc[18])                              # sin 20 sesiones, NaN (no una ventana corta)


def test_91_reglas_por_valor():
    r = list(S.reglas(np.array([0.5, 0.6]), np.array([0.1, 0.2]), [0.1] * 5))
    assert len(r) == 91 and len({n for n, _ in r}) == 91


def _dir(d, rng, alterar_prueba=False):
    for s in ["A", "B"]:
        f = pd.bdate_range("2024-01-02", "2026-06-30")
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, len(f))))
        pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0, "adjclose": c},
                     index=f).to_csv(d / f"velas_{s}.csv")
        i = [k for k in range(len(f)) if f[k] >= pd.Timestamp("2024-07-01") and k + 5 < len(f)]
        ps = rng.choice(np.round(np.arange(0, 1.01, 0.1), 1), len(i))
        p10 = -rng.random(len(i)) * 0.05
        if alterar_prueba:                                              # se inventa el periodo de prueba entero
            prueba = np.array([f[k] >= pd.Timestamp(S.CORTE) for k in i])
            ps = np.where(prueba, 1.0 - ps, ps)
            p10 = np.where(prueba, p10 * 3, p10)
        pd.DataFrame({"fecha": [str(f[k].date()) for k in i], "p_subida": ps, "r_p10": p10, "r_p90": -p10,
                      "r_real": [c[k + 5] / c[k] - 1 for k in i]}).to_csv(d / f"pred_{s}_H5.csv", index=False)


def test_la_eleccion_no_mira_la_prueba(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _dir(tmp_path / "a", np.random.default_rng(1))
    _dir(tmp_path / "b", np.random.default_rng(1), alterar_prueba=True)
    a, b = S.mineria(tmp_path / "a", ["A", "B"], placebos=3), S.mineria(tmp_path / "b", ["A", "B"], placebos=3)
    assert a["elegidas"] == b["elegidas"] and a["desarrollo"]["reglas"] == b["desarrollo"]["reglas"]
    assert a["prueba"]["reglas"] != b["prueba"]["reglas"], "el montaje: la prueba sí cambió"
