"""Fase 2B: el lector de 13F, el traductor CUSIP → símbolo con fecha, el respaldo por nombre, las carteras que imitan
a cada gestor y la selección sin mirar al futuro. Datos sintéticos: ningún dato real en el repo."""
import zipfile

import numpy as np
import pandas as pd
import pytest

from tiresias import buffett as B
from tiresias import gestores as G

SUB = ("ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
       "A1\t14-FEB-2024\t13F-HR\t0001067983\t31-DEC-2023\n"
       "A2\t20-MAR-2024\t13F-HR/A\t0001067983\t31-DEC-2023\n"
       "A3\t12-FEB-2024\t13F-HR\t0000102909\t31-DEC-2023\n"
       "A4\t13-FEB-2024\t13F-NT\t0000999999\t31-DEC-2023\n"
       "A5\t15-FEB-2024\t13F-HR/A\t0000555555\t30-SEP-2023\n")   # enmienda sin su original en el fichero
COV = ("ACCESSION_NUMBER\tREPORTTYPE\tFILINGMANAGER_NAME\n"
       "A1\t13F HOLDINGS REPORT\tBERKSHIRE\nA2\t13F HOLDINGS REPORT\tBERKSHIRE\n"
       "A3\t13F COMBINATION REPORT\tVANGUARD\nA4\t13F NOTICE\tOTRO\nA5\t13F HOLDINGS REPORT\tOTRO\n")
INF = ("ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\n"
       "A1\tAPPLE INC\tCOM\t037833100\t100\t10\tSH\t\n"
       "A1\tAPPLE INC\tCOM\t037833100\t50\t5\tSH\t\n"           # dos líneas del mismo valor: se suman
       "A1\tCOCA COLA CO\tCOM\t191216100\t30\t3\tSH\t\n"
       "A1\tAPPLE INC\tCALL\t037833100\t999\t9\tSH\tCall\n"      # opción: fuera
       "A1\tUS TREASURY\tNOTE\t912828XX1\t500\t500\tPRN\t\n"     # deuda: fuera
       "A2\tAPPLE INC\tCOM\t037833100\t77\t7\tSH\t\n"            # enmienda: fuera
       "A3\tMICROSOFT\tCOM\t594918104\t40\t4\tSH\t\n"
       "A5\tINTEL\tCOM\t458140100\t60\t6\tSH\t\n")


def _zip(tmp_path):
    f = tmp_path / "2024q1_form13f.zip"
    with zipfile.ZipFile(f, "w") as z:
        for nombre, texto in (("SUBMISSION.tsv", SUB), ("COVERPAGE.tsv", COV), ("INFOTABLE.tsv", INF)):
            z.writestr(f"2024q1/{nombre}", texto)
    return f


def test_13f_solo_originales_acciones_y_sin_opciones(tmp_path):
    p = G.leer_13f(_zip(tmp_path))
    assert set(p["accesion"]) == {"A1", "A3"}                         # ni la enmienda ni el aviso
    a1 = p[p["accesion"] == "A1"].set_index("cusip")
    assert a1.loc["037833100", "valor"] == 150 and a1.loc["191216100", "valor"] == 30
    assert "912828XX1" not in a1.index                                 # la deuda, fuera
    assert set(p["cik"]) == {"1067983", "102909"}
    assert a1.loc["037833100", "presentado"] == pd.Timestamp("2024-02-14")
    assert a1.loc["037833100", "periodo"] == pd.Timestamp("2023-12-31")


def test_13f_sin_tabla_falla(tmp_path):
    f = tmp_path / "x.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("SUBMISSION.tsv", SUB)
    with pytest.raises(ValueError, match="COVERPAGE"):
        G.leer_13f(f)


FTD = ("SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
       "20230315|33616C100|FRC|1000|FIRST REPUBLIC BANK|25.0\n"
       "20230503|33616C100|FRCB|500|FIRST REPUBLIC BANK|0.5\n"
       "20221001|90184L102|TWTR|300|TWITTER INC|50.0\n"
       "Trailer record count 3\n")


def test_el_ftd_cuenta_contra_su_recuento_y_no_salta_filas():
    t = G.leer_ftd(FTD)
    assert len(t) == 3 and t.attrs["declaradas"] == 3
    assert t.set_index("simbolo").loc["FRCB", "precio"] == 0.5
    assert np.isnan(G.leer_ftd(FTD.replace("|0.5\n", "|.\n")).set_index("simbolo").loc["FRCB", "precio"])
    con_barra = FTD.replace("TWITTER INC", "TWITTER | INC")                 # una barra en la descripción
    assert len(G.leer_ftd(con_barra)) == 3
    with pytest.raises(ValueError, match="declara 4"):
        G.leer_ftd(FTD.replace("Trailer record count 3", "Trailer record count 4"))
    with pytest.raises(ValueError, match="sin sus seis campos"):
        G.leer_ftd(FTD.replace("20221001|90184L102|TWTR|300|TWITTER INC|50.0", "20221001|90184L102|TWTR"))


def test_una_tabla_13f_con_lineas_que_no_cuadran_falla(tmp_path):
    f = tmp_path / "x.zip"
    roto = INF.replace("A3\tMICROSOFT", "A3\tMICRO\nSOFT")                 # una línea partida en dos
    with zipfile.ZipFile(f, "w") as z:
        for nombre, texto in (("SUBMISSION.tsv", SUB), ("COVERPAGE.tsv", COV), ("INFOTABLE.tsv", roto)):
            z.writestr(nombre, texto)
    with pytest.raises(ValueError, match="INFOTABLE"):
        G.leer_13f(f)


def test_el_traductor_da_el_simbolo_de_esa_fecha():
    t = G.Traductor(G.leer_ftd(FTD))
    assert t.simbolo("33616C100", pd.Timestamp("2023-04-01")) == "FRC"      # antes del cambio
    assert t.simbolo("33616C100", pd.Timestamp("2023-06-01")) == "FRCB"     # después
    assert t.simbolo("90184L102", pd.Timestamp("2022-08-01")) == "TWTR"     # el primero posterior, a 61 días
    assert t.simbolo("90184L102", pd.Timestamp("2022-05-01")) is None       # a más de 90 días: no
    assert t.simbolo("000000000", pd.Timestamp("2022-05-01")) is None


def test_el_respaldo_por_nombre_descarta_lo_ambiguo():
    assert G.normalizar_nombre("Apple Inc. Common Stock") == "APPLE"
    assert G.normalizar_nombre("COCA-COLA CO/THE") == "COCA COLA"
    activos = [("AAPL", "Apple Inc. Common Stock"), ("KO", "Coca-Cola Company (The)"),
               ("ABC", "Alpha Corp"), ("ABD", "ALPHA CORPORATION")]
    m = G.mapa_por_nombre({"037833100": "APPLE INC", "191216100": "COCA COLA CO", "X": "ALPHA CORP"}, activos)
    assert m == {"037833100": "AAPL", "191216100": "KO"}                    # «ALPHA» casa con dos: fuera


def test_mes_de_entrada_es_el_primer_mes_completo():
    assert G.mes_de_entrada(pd.Timestamp("2024-02-14")) == pd.Timestamp("2024-03-31")
    assert G.mes_de_entrada(pd.Timestamp("2024-02-29")) == pd.Timestamp("2024-03-31")
    assert G.mes_de_entrada(pd.Timestamp("2024-03-01")) == pd.Timestamp("2024-04-30")


def _rent(meses=12, n=12):
    idx = pd.date_range("2024-01-31", periods=meses, freq="ME")
    return pd.DataFrame({f"C{j}": [0.01 * (j + 1)] * meses for j in range(n)}, index=idx)


def _pos(cik, presentado, valores, cusips=None):
    cusips = cusips or [f"C{j}" for j in range(len(valores))]
    return pd.DataFrame({"cik": cik, "presentado": pd.Timestamp(presentado), "cusip": cusips, "valor": valores,
                         "emisor": "x", "periodo": pd.Timestamp(presentado), "accesion": f"{cik}{presentado}"})


def test_la_cartera_pesa_por_valor_y_entra_tras_presentarse():
    pos = _pos("1", "2024-02-14", [1.0] * 11 + [9.0])              # 12 posiciones, la última pesa 9/20
    r, cob = G.carteras(pos, _rent())
    s = r["1"].dropna()
    assert s.index[0] == pd.Timestamp("2024-03-31")                 # nada en febrero
    esperado = (sum(0.01 * (j + 1) for j in range(11)) + 9 * 0.12) / 20
    assert s.iloc[0] == pytest.approx(esperado)
    assert len(s) == G.MESES_MAX and bool(cob["entra"].iloc[0])     # sin 13F nuevo: cuatro meses y sale


def test_dura_hasta_el_siguiente_13f():
    pos = pd.concat([_pos("1", "2024-02-14", [1.0] * 12), _pos("1", "2024-05-15", [1.0] * 12)])
    r, _ = G.carteras(pos, _rent())
    s = r["1"].dropna()
    assert list(s.index[:3]) == list(pd.date_range("2024-03-31", periods=3, freq="ME"))
    assert s.index[3] == pd.Timestamp("2024-06-30") and len(s) == 3 + G.MESES_MAX   # el segundo entra en junio


def test_un_13f_atrasado_de_un_periodo_viejo_no_sustituye_al_reciente():
    reciente = _pos("1", "2024-02-14", [1.0] * 12)                                      # periodo 2023-12
    viejo = _pos("1", "2024-03-05", [1.0] * 12, cusips=[f"C{j}" for j in range(11, -1, -1)])
    viejo["periodo"] = pd.Timestamp("2023-06-30")                                       # atrasado
    viejo["valor"] = [100.0] + [1.0] * 11                                               # otra cartera
    r, cob = G.carteras(pd.concat([reciente, viejo]), _rent())
    assert len(cob) == 1 and cob["presentado"].iloc[0] == pd.Timestamp("2024-02-14")
    assert r.loc["2024-04-30", "1"] == pytest.approx(np.mean([0.01 * (j + 1) for j in range(12)]))


def test_sin_cobertura_o_con_pocas_posiciones_no_entra():
    pocas = _pos("2", "2024-02-14", [1.0] * 9)                       # 9 posiciones
    sin_precio = _pos("3", "2024-02-14", [1.0] * 12 + [5.0], cusips=[f"C{j}" for j in range(12)] + ["ZZZ"])
    r, cob = G.carteras(pd.concat([pocas, sin_precio]), _rent())
    c = cob.set_index("cik")
    assert not c.loc["2", "entra"] and c.loc["2", "n"] == 9
    assert not c.loc["3", "entra"] and c.loc["3", "cobertura"] == pytest.approx(12 / 17)
    assert r.empty or ("2" not in r.columns and "3" not in r.columns)


def test_un_valor_que_se_retira_se_reparte():
    rent = _rent()
    rent.loc["2024-05-31":, "C0"] = np.nan                           # C0 deja de cotizar en mayo
    r, _ = G.carteras(_pos("1", "2024-02-14", [1.0] * 12), rent)
    mayo = r.loc["2024-05-31", "1"]
    assert mayo == pytest.approx(np.mean([0.01 * (j + 1) for j in range(1, 12)]))


def _gestores(n_meses=60, n=20, semilla=5):
    rng = np.random.default_rng(semilla)
    idx = pd.date_range("2016-01-31", periods=n_meses, freq="ME")
    F = pd.DataFrame(rng.normal(0.005, 0.04, (n_meses, 6)), index=idx, columns=G.SEIS)
    F["RF"] = 0.001
    r = pd.DataFrame({str(k): F["RF"] + (0.002 * k / n) + 0.9 * F["MKT"] + rng.normal(0, 0.02, n_meses)
                      for k in range(n)}, index=idx)
    return r, F


def test_las_decisiones_no_miran_al_futuro():
    r, F = _gestores()
    a = G.decisiones(r, F, "2019-01-31")
    r2 = r.copy()
    d0 = a[0][0]
    r2.loc[d0 + pd.offsets.MonthEnd(1):] = 0.5                        # lo de después de la primera decisión cambia…
    b = G.decisiones(r2, F, "2019-01-31")
    assert a[0][0] == b[0][0] and a[0][1].keys() == b[0][1].keys()
    assert all(a[0][1][c]["t"] == b[0][1][c]["t"] for c in a[0][1])   # …y la primera decisión, no
    assert d0 == pd.Timestamp("2018-12-31")


def test_el_decil_elige_los_de_mayor_t():
    info = {str(k): {"t": float(k)} for k in range(20)}
    assert G.elegir_decil(info) == ["19", "18"]
    assert len(G.elegir_azar(1)(info)) == 2 and G.elegir_todos(info) == list(info)


def test_la_receta_cubre_los_tres_meses_siguientes():
    r, F = _gestores()
    decs = G.decisiones(r, F, "2019-01-31")
    rec = G.receta(decs, F, G.elegir_decil)
    assert rec.index[0] == pd.Timestamp("2019-01-31")
    assert len(rec) == len(F.loc["2019-01-31":])


def _serie(media, n=96, semilla=0, desde="2019-01-31"):
    rng = np.random.default_rng(semilla)
    return pd.Series(media + rng.normal(0, 0.03, n), index=pd.date_range(desde, periods=n, freq="ME"))


def test_veredicto_pasa_solo_con_las_cuatro():
    rf = pd.Series(0.001, index=pd.date_range("2019-01-31", periods=96, freq="ME"))
    sp = _serie(0.006, semilla=1)
    buena = sp + 0.006                                                  # misma volatilidad, más exceso
    v = G.veredicto(buena, sp, sp + 0.001, [0.1] * 200, rf)
    assert v["pasa"] and v["cumplidos"] == 4
    assert not G.veredicto(buena, sp, buena, [0.1] * 200, rf)["criterios"]["4_sobre_todos_los_gestores"]
    assert not G.veredicto(buena, sp, sp, [5.0] * 200, rf)["criterios"]["3_sobre_el_placebo_p95"]
    mala_mitad = buena.copy()
    mala_mitad.iloc[48:] = sp.iloc[48:] - 0.002
    assert not G.veredicto(mala_mitad, sp, sp, [0.1] * 200, rf)["criterios"]["2_en_las_dos_mitades"]


def test_la_regla_de_parada_pondera_por_valor_y_cuenta_trimestres():
    def cob(filas):
        return pd.DataFrame(filas, columns=["presentado", "cobertura", "valor"])
    # 4 trimestres; el segundo, 0,80 ponderado (0,95 de 1 y 0,79 de 9 → 0,806): uno de cuatro no para
    base = [("2016-02-14", 0.95, 1.0), ("2016-02-15", 0.95, 1.0), ("2016-05-14", 0.95, 1.0), ("2016-05-15", 0.79, 9.0),
            ("2016-08-14", 0.95, 1.0), ("2016-11-14", 0.95, 1.0)]
    r = G.parada(cob(base))
    assert r["trimestres"] == 4 and r["bajos"] == 1 and not r["para"]
    assert r["por_trimestre"].iloc[1] == pytest.approx((0.95 + 0.79 * 9) / 10)
    # sin ponderar, el segundo saldría 0,87 y no contaría: con dos bajos de cuatro, para
    r = G.parada(cob(base + [("2016-08-15", 0.10, 5.0)]))
    assert r["bajos"] == 2 and r["para"]


def test_la_receta_con_pesos_medios_es_la_media_de_las_estrategias():
    """La referencia es el cálculo de antes: aplicar la estrategia de cada elegido y promediar."""
    rng = np.random.default_rng(3)
    idx = pd.date_range("2016-01-31", periods=40, freq="ME")
    F = pd.DataFrame(rng.normal(0.005, 0.03, (40, 6)), index=idx, columns=G.SEIS)
    F["RF"] = 0.001
    p = lambda: {"beta": rng.normal(1, .2), "cargas": {f: rng.normal(0, .3) for f in G.SEIS},
                 "escala": abs(rng.normal(1, .3)), "sigma_idio": .02}
    decs = [(d, {str(c): {"t": rng.normal(), "p": p()} for c in range(30)}) for d in idx[5::3][:8]]
    r = G.receta(decs, F, G.elegir_todos)
    ref = {}
    for k, (d, info) in enumerate(decs):
        sig = F.loc[d:].iloc[1:4]
        if k + 1 < len(decs):
            sig = sig.loc[:decs[k + 1][0]]
        for m in sig.index:
            ref[m] = np.mean([B.aplicar_estilo(sig.loc[[m]], info[c]["p"]).iloc[0] for c in info])
    ref = pd.Series(ref).sort_index()
    assert list(r.index) == list(ref.index) and np.allclose(r.to_numpy(), ref.to_numpy(), rtol=0, atol=1e-14)
