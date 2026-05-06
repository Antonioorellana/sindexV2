import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.conciliacion import conciliar_mes, obtener_casos_por_estado, resumen_conciliacion
from db.database import get_connection, initialize_database
from ui.app import construir_texto_conciliacion


def _crear_db_temporal(base_dir: Path) -> Path:
    db_path = base_dir / "sindicato.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.executemany(
            "INSERT INTO socios (rut, nombre, local, activo, mes_carga) VALUES (?, ?, ?, ?, ?)",
            [
                ("15375441-1", "ORELLANA VERAGUA, ANTONIO SEBASTIAN", "(J760) Jumbo Copiapo", 1, "2026-05"),
                ("11111111-1", "SOCIO UNO", "(J760) Jumbo Copiapo", 1, "2026-05"),
                ("22222222-2", "SOCIO DOS", "(J760) Jumbo Copiapo", 1, "2026-05"),
            ],
        )
        connection.executemany(
            "INSERT INTO funs_enviado (mes, rut, nombre, motivo, monto) VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-04", "15375441-1", "ORELLANA VERAGUA, ANTONIO SEBASTIAN", "Capual", 126000),
                ("2026-04", "11111111-1", "SOCIO UNO", "Optica", 20000),
            ],
        )
        connection.executemany(
            "INSERT INTO cesjun_descuentos (mes, rut, nombre, monto) VALUES (?, ?, ?, ?)",
            [
                ("2026-04", "15375441-1", "ORELLANA VERAGUA, ANTONIO SEBASTIAN", 126000),
                ("2026-04", "22222222-2", "SOCIO DOS", 15000),
            ],
        )
    return db_path


class ConciliacionTests(unittest.TestCase):
    def test_conciliar_mes_y_resumen(self):
        with TemporaryDirectory() as tmp:
            db_path = _crear_db_temporal(Path(tmp))
            resultado = conciliar_mes("2026-04", db_path)
            resumen = resumen_conciliacion("2026-04", db_path)
        self.assertEqual(resultado["casos_conciliados"], 3)
        self.assertEqual(resumen["total_enviado_funs"], 146000)
        self.assertEqual(resumen["total_descontado_cesjun"], 141000)
        self.assertEqual(resumen["estados"], {"inesperado": 1, "no_descontado": 1, "ok": 1})

    def test_obtener_no_descontados_y_texto(self):
        with TemporaryDirectory() as tmp:
            db_path = _crear_db_temporal(Path(tmp))
            conciliar_mes("2026-04", db_path)
            resumen = resumen_conciliacion("2026-04", db_path)
            casos = obtener_casos_por_estado("2026-04", "no_descontado", db_path)
            texto = construir_texto_conciliacion("2026-04", resumen, casos)
        self.assertEqual(len(casos), 1)
        self.assertIn("Casos no descontados:", texto)
        self.assertIn("11111111-1 | SOCIO UNO", texto)
        self.assertIn("FUNS: $20.000", texto)


if __name__ == "__main__":
    unittest.main()
