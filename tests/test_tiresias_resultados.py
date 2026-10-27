"""TiresIAs: el recuento de criterios se cuenta, no se compone."""
from tiresias import resultados as R


def test_criterios_cuenta_los_cumplidos():
    c = {"1 a": False, "2 b": False, "3 c": False, "4 d": True}
    assert R.criterios(c) == "1 de 4 (el 4.º)"                 # y no «4 de 4»
    assert R.criterios({k: False for k in c}) == "0 de 4"
    assert R.criterios({k: True for k in c}) == "4 de 4 (el 1.º, el 2.º, el 3.º, el 4.º)"
