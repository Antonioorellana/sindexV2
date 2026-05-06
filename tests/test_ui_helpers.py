import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ui.app import _parsear_periodo, buscar_archivo_en_archivos, resolver_ruta_archivo


class UiHelpersTests(unittest.TestCase):
    def test_buscar_archivo_en_archivos_es_case_insensitive(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archivo = base / "cesjun.xlsx"
            archivo.write_text("ok", encoding="utf-8")
            encontrado = buscar_archivo_en_archivos(["CESJUN.xlsx"], base)
        self.assertEqual(encontrado, archivo)

    def test_resolver_ruta_archivo_prefiere_ruta_existente(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archivo = base / "otro.xlsx"
            archivo.write_text("ok", encoding="utf-8")
            resuelto = resolver_ruta_archivo(str(archivo), ["FUNS.xlsx"], base)
        self.assertEqual(resuelto, archivo)

    def test_parsear_periodo_valido(self):
        self.assertEqual(_parsear_periodo("2026-05"), (2026, 5))


if __name__ == "__main__":
    unittest.main()
