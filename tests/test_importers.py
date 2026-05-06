import unittest

from core.importers import _entero


class ImportersTests(unittest.TestCase):
    def test_entero_respeta_numeros_de_excel(self):
        self.assertEqual(_entero(126000.0), 126000)
        self.assertEqual(_entero(126000), 126000)

    def test_entero_limpia_formatos_chilenos(self):
        self.assertEqual(_entero("$126.000"), 126000)
        self.assertEqual(_entero("126000.0"), 126000)


if __name__ == "__main__":
    unittest.main()
