"""TiresIAs: las piezas del informe en PDF que deciden qué se escribe."""
from tiresias import informe_pdf as P


def test_cifras_signo_y_cero_negativo():
    cf = P.Cifras()
    assert cf.n(-0.0123, 3, True) == r"\textminus{}0,012" and cf.n(0.0123, 3, True) == "+0,012"
    assert cf.n(-0.0004, 3) == "0,000"                     # un −0,000 diría que es negativo lo que redondea a 0
    assert cf.emitidas == ["−0,012", "+0,012", "0,000"]
    assert cf.pct(0.256) == r"26\,\%" and cf.emitidas[-1] == "26"


def test_criterios_ninguno_y_alguno():
    nada = {"1 a": False, "2 b": False, "3 c": False, "4 d": False}
    assert P._criterios(nada, "a 5 sesiones") == "a 5 sesiones no se cumple ninguno"
    assert "el 4.º (al menos 3 de 5" in P._criterios({**nada, "4 d": True}, "a 1 sesión")


def _v(ic_lo, cagr_k, cagr_bh):
    return {"S": {5: {"ic90": (ic_lo, 0.1)}}}, {"H5": {"por_valor": {"S": {"cagr_kronos": cagr_k, "cagr_mantener": cagr_bh}}}}


def test_el_titular_negativo_tiene_su_rama():
    assert P.es_negativo(*_v(-0.01, 0.05, 0.10), ["S"])
    assert not P.es_negativo(*_v(0.01, 0.05, 0.10), ["S"])         # RankIC distinguible de 0
    assert not P.es_negativo(*_v(-0.01, 0.12, 0.10), ["S"])        # operado rinde más que mantenido
