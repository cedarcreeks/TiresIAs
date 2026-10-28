"""TiresIAs: las piezas del informe final que deciden qué se dice."""
from tiresias import informe_final as F


def test_comparador_apunta_lo_que_no_cuadra():
    c = F.Comparador()
    c("a", 1.0, 1.0 + 1e-12)
    c("b", 1.0, 1.1)
    assert c.n == 2 and len(c.fallos) == 1 and c.fallos[0].startswith("b:")


def test_criterios_sp_cuenta():
    sp = {"condiciones": {"1 x": True, "2 y": False, "3 z": False}}
    assert F._criterios_sp(sp) == "cumple 1 de 3 criterios del plan"


def test_escapa_lo_que_rompe_latex():
    assert F._esc("A&B 5% x_y") == r"A\&B 5\% x\_y"


def _rep(kp, np_, kr=0.04, nr=0.02, distintas=0):
    return {"media": {"k_ric_precios": kp, "n_ric_precios": np_, "k_ric_rentab": kr, "n_ric_rentab": nr},
            "por_valor": {"A": {"predicciones_distintas_de_lo_guardado": distintas}}}


DIAG = {"semanas": 116, "minima_detectable": 0.021, "ic90": (-0.015, 0.02), "fiabilidad_mediana": 0.92,
        "kronos_vs_ultima_semana": -0.4, "reversion_ic": 0.003, "reversion_t": 0.19}


def test_seccion_algo_mal_cada_rama():
    from tiresias import informe_pdf as B
    txt = lambda r: "\n".join(F.seccion_algo_mal(B.Cifras(), DIAG, r))          # noqa: E731
    a = txt(_rep(0.012, 0.020, 0.038, 0.016))
    assert "En precios, la recta saca tanto o más; en rentabilidad paso a paso, gana Kronos" in a
    assert "En precios, gana Kronos; en rentabilidad paso a paso, la recta saca tanto o más" in txt(_rep(0.03, 0.02, 0.01, 0.02))
    assert "al último bit" in a and "reentrena" in a
    assert "alguna predicción rehecha no coincide" in txt(_rep(0.012, 0.02, distintas=1))
