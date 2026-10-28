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


def _rep(k, n, distintas=0):
    return {"media": {"k_ric_precios": k, "n_ric_precios": n, "k_ric_rentab": 0.01},
            "por_valor": {"A": {"predicciones_distintas_de_lo_guardado": distintas}}}


DIAG = {"semanas": 116, "minima_detectable": 0.021, "ic90": (-0.015, 0.02), "fiabilidad_mediana": 0.92,
        "kronos_vs_ultima_semana": -0.4, "reversion_ic": 0.003, "reversion_t": 0.19}


def test_seccion_algo_mal_cada_rama():
    from tiresias import informe_pdf as B
    gana_recta = "\n".join(F.seccion_algo_mal(B.Cifras(), DIAG, _rep(0.02, 0.03)))
    gana_kronos = "\n".join(F.seccion_algo_mal(B.Cifras(), DIAG, _rep(0.03, 0.02)))
    assert "La recta ingenua saca tanto o más" in gana_recta and "Kronos saca algo más" in gana_kronos
    assert "al último bit" in gana_recta
    assert "alguna predicción rehecha no coincide" in "\n".join(F.seccion_algo_mal(B.Cifras(), DIAG, _rep(0.02, 0.03, 1)))
