"""Tests de tiresias.congreso: el índice del Clerk y la descarga reanudable de las declaraciones."""
import io
import urllib.error
import zipfile

from tiresias import congreso as C

CAB = "Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n"


def test_el_indice_solo_trae_las_declaraciones_de_operaciones(tmp_path):
    f = tmp_path / "2024FD.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("2024FD.txt", CAB + "Hon.\tAllen\tRichard W.\t\tP\tGA12\t2024\t1/11/2024\t20024277\n"
                                       "Hon.\tOtro\tX\t\tO\tCA01\t2024\t5/15/2024\t10059999\n")
    r = C.indice(f)
    assert r == [{"apellido": "Allen", "nombre": "Richard W.", "distrito": "GA12", "presentado": "1/11/2024",
                  "docid": "20024277", "anio": "2024"}]


class _Red:
    def __init__(self, respuestas):
        self.respuestas, self.pedidas = list(respuestas), []

    def __call__(self, req):
        self.pedidas.append(req.full_url)
        x = self.respuestas.pop(0)
        if isinstance(x, int):
            raise urllib.error.HTTPError(req.full_url, x, "x", {}, io.BytesIO(b""))
        return x


def test_la_descarga_reanuda_y_no_repite_un_404(tmp_path):
    ptrs = [{"docid": "1", "anio": "2024"}, {"docid": "2", "anio": "2024"}]
    red = _Red([b"%PDF-1", 404])
    r = C.descargar(ptrs, tmp_path, abrir=red, dormir=lambda _: None)
    assert r == {"bajados": 1, "ya_estaban": 0, "faltan": 1}
    assert (tmp_path / "2024" / "1.pdf").read_bytes() == b"%PDF-1" and red.pedidas[0].endswith("/ptr-pdfs/2024/1.pdf")
    red2 = _Red([])
    assert C.descargar(ptrs, tmp_path, abrir=red2, dormir=lambda _: None) == {"bajados": 0, "ya_estaban": 2, "faltan": 1}
    assert red2.pedidas == [] and not list(tmp_path.rglob("*.tmp"))


# Un texto sintético con el formato de `pdftotext -layout` de una PTR electrónica (sin datos reales en el repo).
PTR = """
ID         Owner Asset                                   Transaction Date                 Notification Amount
           SP         Acme Corporation (ACME) [ST]            S                 12/21/2023 01/08/2024             $1,001 - $15,000
                      F      S       : New
           JT         Beta Holdings Inc. (BETA) P                           12/14/2023 01/08/2024             $50,001 -
                      [ST]                                                                                            $100,000
                      Gamma Corp. Class B
                      (GAM.B) [ST]                            S (partial)        11/02/2023 01/08/2024             $15,001 -
           SP         Some Bond Fund [MF]                     P                 12/01/2023 01/08/2024             $1,001 - $15,000
"""


def test_las_operaciones_de_una_ptr_con_lineas_partidas():
    ops = C.operaciones(PTR)
    assert [o["ticker"] for o in ops] == ["ACME", "BETA", "GAM.B", None]
    assert [o["tipo"] for o in ops] == ["S", "P", "S", "P"]
    assert [o["clase"] for o in ops] == ["ST", "ST", "ST", "MF"]                 # el [ST] partido, a la línea de abajo
    assert ops[1]["importe_min"] == 50001 and ops[1]["importe_max"] == 100000    # el máximo partido sale del tramo
    assert ops[0]["fecha_operacion"] == "12/21/2023" and ops[0]["fecha_notificacion"] == "01/08/2024"


# El formato de 2016: mayúsculas rotas por la fuente, tipo en minúscula, días de una cifra, símbolo partido abajo.
PTR_2016 = """
           JT       aT&T Inc. (T)                               P                 10/10/2016 10/10/2016           $1,001 - $15,000
                    FIlINg sTaTus: New
           JT       Baxter International Inc. (BaX)             s                 08/31/2016 08/31/2016           $1,001 - $15,000
                    lee Enterprises, Incorporated (lEE)         s                 09/7/2016      09/7/2016        $1,001 - $15,000
           JT       Twenty-First Century Fox, Inc. - Class a P                    08/31/2016 08/31/2016           $1,001 - $15,000
                    (FOXa)
           SP       Omega Inc. (OMG) [OP]                       S (partial)       01/05/2016 01/20/2016           $15,001 - $50,000
"""


def test_el_formato_de_2016():
    ops = C.operaciones(PTR_2016)
    assert [o["ticker"] for o in ops] == ["T", "BAX", "LEE", "FOXA", "OMG"]
    assert [o["tipo"] for o in ops] == ["P", "S", "S", "P", "S"]
    assert ops[2]["fecha_operacion"] == "09/7/2016" and ops[4]["clase"] == "OP"
