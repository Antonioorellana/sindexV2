import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.descuentos import aplicar_cuota_mensual_masiva, guardar_descuento_mensual, listar_descuentos_mes
from db.database import get_connection, initialize_database


class DescuentosTests(unittest.TestCase):
    def test_guardar_descuento_exige_socio_existente(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            with self.assertRaises(sqlite3.IntegrityError):
                guardar_descuento_mensual("99999999-9", "2026-05", "Otro", 1000, "", db_path)

    def test_aplicar_cuota_mensual_masiva_usa_monto_8000_por_defecto(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            with get_connection(db_path) as connection:
                connection.execute(
                    "INSERT INTO socios (rut, nombre, local, activo, mes_carga) VALUES (?, ?, ?, ?, ?)",
                    ("15375441-1", "SOCIO TEST", "LOCAL", 1, "2026-05"),
                )

            cantidad = aplicar_cuota_mensual_masiva("2026-05", db_path=db_path)
            descuentos = listar_descuentos_mes("2026-05", db_path)

        self.assertEqual(cantidad, 1)
        self.assertEqual(descuentos[0]["tipo"], "Cuota mensual")
        self.assertEqual(descuentos[0]["monto"], 8000)


if __name__ == "__main__":
    unittest.main()
