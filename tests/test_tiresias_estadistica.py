"""TiresIAs: la t exacta contra tabla y Holm."""
import math

import pytest

from tiresias import estadistica as E


@pytest.mark.parametrize("t, gl, p", [(1.812461, 10, 0.05), (2.228139, 10, 0.025), (2.045230, 29, 0.025),
                                      (1.660234, 100, 0.05), (0.0, 7, 0.5)])
def test_t_contra_tabla(t, gl, p):
    assert E.p_t(t, gl) == pytest.approx(p, abs=1e-6)


def test_cola_izquierda_y_negativa():
    assert E.p_t(-1.812461, 10) == pytest.approx(0.95, abs=1e-6)
    assert E.p_t(-1.812461, 10, "izquierda") == pytest.approx(0.05, abs=1e-6)


def test_holm():
    r = E.holm({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.04, "e": 0.2})
    assert r == {"a": True, "b": False, "c": False, "d": False, "e": False}      # 0,02 > 0,05/4 corta la cadena
    assert E.holm({"a": 0.009, "b": 0.012})["b"] is True and E.holm({"x": math.nan, "y": 0.01})["x"] is False
