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
