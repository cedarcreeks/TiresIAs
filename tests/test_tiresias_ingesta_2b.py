"""Tests de tiresias.ingesta_2b: FTD de varios ficheros, 13F reanudable y la unión sin duplicados. Datos sintéticos."""
import json
import zipfile

import pandas as pd
import pytest

from tiresias import ingesta_2b as I

CAB = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"


def _ftd(tmp_path, nombre, filas, declaradas=None):
    texto = CAB + "".join(filas) + f"Trailer record count {len(filas) if declaradas is None else declaradas}\n"
    f = tmp_path / nombre
    with zipfile.ZipFile(f, "w") as z:
        z.writestr(nombre.replace(".zip", ".txt"), texto)
    return f


def test_ftd_une_ficheros_sin_duplicados_y_con_su_informe(tmp_path):
    a = _ftd(tmp_path, "cnsfails202301a.zip", ["20230103|037833100|AAPL|10|APPLE INC|125\n",
                                              "20230104|037833100|AAPL|20|APPLE INC|126\n"])
    b = _ftd(tmp_path, "cnsfails202301b.zip", ["20230104|037833100|AAPL|20|APPLE INC|126\n",      # repetida
                                              "20230117|30303M102|META|5|META PLATFORMS|136\n"])
    tabla, informe = I.ftd([b, a])
    assert len(tabla) == 3 and [x["fichero"] for x in informe] == ["cnsfails202301a.zip", "cnsfails202301b.zip"]
    assert [x["filas"] for x in informe] == [2, 2] and [x["declaradas"] for x in informe] == [2, 2]


def test_un_ftd_sin_extension_vale_y_dos_ficheros_sin_txt_no(tmp_path):
    f = tmp_path / "cnsfails202205b.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("cnsfails202205b", CAB + "20220516|037833100|AAPL|10|APPLE INC|145\nTrailer record count 1\n")
    assert len(I.ftd([f])[0]) == 1
    g = tmp_path / "cnsfails202206b.zip"
    with zipfile.ZipFile(g, "w") as z:
        z.writestr("a", "x")
        z.writestr("b", "y")
    with pytest.raises(ValueError, match="un fichero de datos"):
        I.ftd([g])


def test_un_ftd_que_no_cuadra_con_su_recuento_para(tmp_path):
    with pytest.raises(ValueError, match="declara"):
        I.ftd([_ftd(tmp_path, "cnsfails202301a.zip", ["20230103|037833100|AAPL|10|APPLE INC|125\n"], declaradas=5)])


SUB = "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
COV = "ACCESSION_NUMBER\tREPORTTYPE\n"
INF = "ACCESSION_NUMBER\tNAMEOFISSUER\tCUSIP\tVALUE\tSSHPRNAMTTYPE\tPUTCALL\n"


def _13f(tmp_path, nombre, presentaciones):
    """presentaciones: [(accesión, fecha, cik, periodo)], cada una con una posición."""
    sub = SUB + "".join(f"{a}\t{f}\t13F-HR\t{c}\t{p}\n" for a, f, c, p in presentaciones)
    cov = COV + "".join(f"{a}\t13F HOLDINGS REPORT\n" for a, *_ in presentaciones)
    inf = INF + "".join(f"{a}\tX\t037833100\t10\tSH\t\n" for a, *_ in presentaciones)
    f = tmp_path / nombre
    with zipfile.ZipFile(f, "w") as z:
        for n, t in (("SUBMISSION.tsv", sub), ("COVERPAGE.tsv", cov), ("INFOTABLE.tsv", inf)):
            z.writestr(n, t)
    return f


def test_trece_f_es_reanudable_y_relee_si_cambia_el_origen(tmp_path):
    z = _13f(tmp_path, "2016q1_form13f.zip", [("A1", "14-FEB-2016", "0000000001", "31-DEC-2015")])
    d = tmp_path / "pq"
    pq, = I.trece_f([z], d)
    meta = json.loads((d / "2016q1_form13f.json").read_text())
    assert meta["posiciones"] == 1 and len(meta["sha256"]) == 64
    marca = pq.stat().st_mtime_ns
    I.trece_f([z], d)
    assert pq.stat().st_mtime_ns == marca                                   # mismo origen: no se relee
    _13f(tmp_path, "2016q1_form13f.zip", [("A1", "14-FEB-2016", "0000000001", "31-DEC-2015"),
                                         ("A2", "15-FEB-2016", "0000000002", "31-DEC-2015")])
    I.trece_f([z], d)
    assert len(pd.read_parquet(pq)) == 2                                    # otro origen: se relee


def test_posiciones_un_original_por_periodo_entre_ficheros_y_desde_2016(tmp_path):
    a = _13f(tmp_path, "2015q4_form13f.zip", [("A0", "10-NOV-2015", "0000000001", "30-SEP-2015")])
    b = _13f(tmp_path, "2016q1_form13f.zip", [("A1", "14-FEB-2016", "0000000001", "31-DEC-2015")])
    c = _13f(tmp_path, "2016q2_form13f.zip", [("A2", "05-APR-2016", "0000000001", "31-DEC-2015"),   # repetido, después
                                             ("A3", "10-MAY-2016", "0000000001", "31-MAR-2016")])
    p = I.posiciones(I.trece_f([a, b, c], tmp_path / "pq"))
    assert sorted(p["accesion"]) == ["A1", "A3"]
