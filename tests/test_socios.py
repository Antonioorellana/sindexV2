import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.socios import buscar_socio_por_rut, guardar_socios_desde_sijuan, listar_socios, obtener_resumen_socios
from db.database import initialize_database


class SociosTests(unittest.TestCase):
    def test_guardar_listar_y_resumen_socios(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            resultado = guardar_socios_desde_sijuan(
                [
                    {"rut": "15375441-1", "nombre": "ORELLANA VERAGUA, ANTONIO SEBASTIAN", "local": "Jumbo Copiapo"},
                    {"rut": "11111111-1", "nombre": "SOCIO UNO", "local": "Jumbo Copiapo"},
                    {"rut": "11111111-1", "nombre": "SOCIO UNO DUP", "local": "Jumbo Copiapo"},
                ],
                "2026-05",
                db_path,
            )
            activos = listar_socios(activo=True, limite=10, db_path=db_path)
            socio = buscar_socio_por_rut("15375441-1", db_path)
            resumen = obtener_resumen_socios(db_path)

        self.assertEqual(resultado["socios_activos"], 2)
        self.assertEqual(resultado["duplicados_omitidos"], 1)
        self.assertEqual(len(activos), 2)
        self.assertEqual(socio["nombre"], "ORELLANA VERAGUA, ANTONIO SEBASTIAN")
        self.assertEqual(resumen["total"], 2)
        self.assertEqual(resumen["activos"], 2)
        self.assertEqual(resumen["ultimo_mes"], "2026-05")
        self.assertEqual(resumen["top_locales"][0]["local"], "Jumbo Copiapo")


if __name__ == "__main__":
    unittest.main()
