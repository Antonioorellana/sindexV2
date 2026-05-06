import unittest

from core.ruts import normalizar_rut, preparar_rut_para_busqueda, validar_rut


class RutTests(unittest.TestCase):
    def test_normalizar_rut_con_puntos_y_guion(self):
        self.assertEqual(normalizar_rut("15.375.441-1"), "15375441-1")

    def test_normalizar_rut_con_dv_k(self):
        self.assertEqual(normalizar_rut("9.069.734-k"), "9069734-K")

    def test_validar_rut_valido(self):
        self.assertTrue(validar_rut("15375441-1"))

    def test_validar_rut_invalido(self):
        self.assertFalse(validar_rut("15375441-2"))

    def test_preparar_rut_para_busqueda(self):
        self.assertEqual(preparar_rut_para_busqueda("153754411"), "15375441-1")


if __name__ == "__main__":
    unittest.main()

