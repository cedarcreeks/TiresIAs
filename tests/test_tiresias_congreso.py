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
