"""TiresIAs: el reentrenamiento. Nada posterior al preentrenamiento entra, los bucles corren, guardan y se reanudan."""
import json
import pickle

import numpy as np
import pandas as pd
import pytest

from tiresias import reentrenar as RE


def _velas(d, simbolos=("A", "B")):
    rng = np.random.default_rng(0)
    f = pd.bdate_range("2010-01-04", "2025-12-31")
    for s in simbolos:
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(f))))
        pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6, "adjclose": c},
                     index=f).to_csv(d / f"velas_{s}.csv")
    (d / "simbolos.json").write_text(json.dumps({"simbolos": list(simbolos)}))


def test_preparar_no_deja_pasar_nada_posterior(tmp_path):
    _velas(tmp_path)
    r = RE.preparar(tmp_path, tmp_path / "p")
    for nombre, (a, b) in (("train", RE.ENTRENA), ("val", RE.VALIDA)):
        datos = pickle.load(open(tmp_path / "p" / f"{nombre}_data.pkl", "rb"))
        for df in datos.values():
            assert df.index.min() >= pd.Timestamp(a) and df.index.max() <= pd.Timestamp(b)
            assert list(df.columns) == RE.COLS and df.index.name == "datetime"
    assert r["ultima_fecha"] <= "2024-06-30"


def test_los_bucles_corren_guardan_y_reanudan(tmp_path):
    _velas(tmp_path)
    RE.preparar(tmp_path, tmp_path / "p")
    cfg = RE.Config(str(tmp_path / "p"), epocas=2, lote=4)
    cfg.n_train_iter, cfg.n_val_iter = 8, 8
    t = RE.tokenizador(cfg, "cpu", tmp_path / "p")
    assert (tmp_path / "p" / "tokenizador_mejor").exists() and np.isfinite(t["mejor_val"])
    p = RE.predictor(cfg, "cpu", tmp_path / "p", hasta=1)                # se «corta» tras la primera época
    assert (tmp_path / "p" / "predictor_mejor").exists() and len(p["historial"]) == 1
    p2 = RE.predictor(cfg, "cpu", tmp_path / "p")                        # reanuda: sólo hace la segunda
    assert [h["epoca"] for h in p2["historial"]] == [1, 2] and np.isfinite(p2["mejor_val"])
    cfg.epochs = 3
    with pytest.raises(SystemExit):                                     # con otro plan de épocas, no reanuda
        RE.predictor(cfg, "cpu", tmp_path / "p")


def test_el_control_reproduce_la_pérdida_apuntada_al_guardar(tmp_path, monkeypatch):
    """Con los pesos guardados, la pérdida de validación tiene que ser la que el bucle apuntó: si no, se mide otra cosa
    o se cargan otros pesos. Y el original no es el reentrenado (si lo fuera, el reentreno no se habría cargado).
    Kronos.forward, sin teacher forcing (como entrenan sus autores), condiciona s2 a un s1 MUESTREADO: la pérdida del
    predictor tiene ruido, que con 8 muestras pasa de 1e-4 y con 20.000 queda en 2e-7 (medido el 29-oct). Aquí se quita el
    muestreo para que la comparación sea exacta y pruebe la fontanería."""
    import torch
    monkeypatch.setattr(torch, "multinomial", lambda p, n: p.argmax(dim=-1, keepdim=True))
    _velas(tmp_path)
    RE.preparar(tmp_path, tmp_path / "p")
    cfg = RE.Config(str(tmp_path / "p"), epocas=1, lote=4)
    cfg.n_train_iter, cfg.n_val_iter = 8, 8
    t = RE.tokenizador(cfg, "cpu", tmp_path / "p")
    p = RE.predictor(cfg, "cpu", tmp_path / "p")
    r = RE.controlar(cfg, "cpu", tmp_path / "p")
    assert r["tokenizador"]["reentrenado"] == pytest.approx(t["mejor_val"], rel=1e-6)
    assert r["predictor"]["reentrenado"] == pytest.approx(p["mejor_val"], rel=1e-6)
    assert r["tokenizador"]["original"] != pytest.approx(r["tokenizador"]["reentrenado"], rel=1e-6)
    assert r["predictor"]["original"] != pytest.approx(r["predictor"]["reentrenado"], rel=1e-6)
