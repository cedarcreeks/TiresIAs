"""TiresIAs: el corte de los datos y la sesión a medias."""
import datetime as dt

import pytest

from tiresias import datos as D


def _resp(fechas, cierres, inicio, fin):
    ts = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())  # noqa: E731
    return {"chart": {"result": [{"timestamp": [ts(f + "T13:30") for f in fechas],
                                  "meta": {"currentTradingPeriod": {"regular": {"start": ts(inicio), "end": ts(fin)}}},
                                  "indicators": {"quote": [{"open": cierres, "high": cierres, "low": cierres,
                                                            "close": cierres, "volume": [None] * len(cierres)}],
                                                 "adjclose": [{"adjclose": [c * 0.9 for c in cierres]}]}}]}}


def _t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()


def test_corta_en_fin_y_rellena_el_volumen():
    r = _resp(["2026-10-22", "2026-10-23", "2026-10-26"], [1.0, 2.0, 3.0], "2026-10-26T13:30", "2026-10-26T20:00")
    df = D.leer(r, "2026-10-23", _t("2026-10-26T16:00"))       # el 26 a medias, pero fuera del corte
    assert list(df["close"]) == [1.0, 2.0] and (df["volume"] == 0).all() and list(df["adjclose"]) == [0.9, 1.8]


def test_la_sesión_a_medias_dentro_del_corte_es_un_error():
    r = _resp(["2026-10-23", "2026-10-26"], [2.0, 3.0], "2026-10-26T13:30", "2026-10-26T20:00")
    with pytest.raises(ValueError, match="abierta"):
        D.leer(r, "2026-10-26", _t("2026-10-26T16:00"))
    assert len(D.leer(r, "2026-10-26", _t("2026-10-26T21:00"))) == 2        # bajada tras el cierre: vale
