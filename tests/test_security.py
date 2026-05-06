import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.security import (
    cambiar_password_usuario,
    crear_backup_automatico,
    crear_usuario,
    crear_usuario_basico,
    desactivar_usuario,
    guardar_password_admin,
    listar_eventos_recientes,
    listar_usuarios,
    login_configurado,
    registrar_evento,
    registrar_uso_password_inicial,
    verificar_usuario,
    verificar_password_admin,
)
from db.database import initialize_database


class SecurityTests(unittest.TestCase):
    def test_password_admin_se_guarda_hasheada_y_verifica(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            self.assertFalse(login_configurado(db_path))
            guardar_password_admin("secreto123", db_path)

            self.assertTrue(login_configurado(db_path))
            self.assertTrue(verificar_password_admin("secreto123", db_path))
            self.assertFalse(verificar_password_admin("otro", db_path))

    def test_crear_usuario_basico_y_desactivar(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            crear_usuario("operador", "clave123", "basico", db_path)
            usuario = verificar_usuario("operador", "clave123", db_path)
            usuarios = listar_usuarios(db_path)
            desactivar_usuario("operador", db_path)
            desactivado = verificar_usuario("operador", "clave123", db_path)

        self.assertEqual(usuario["rol"], "basico")
        self.assertEqual(usuarios[0]["username"], "operador")
        self.assertIsNone(desactivado)

    def test_usuario_basico_desde_nombre_usa_formato_y_password_1234(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            username = crear_usuario_basico("Antonio Orellana", db_path)
            usuario = verificar_usuario(username, "1234", db_path)
            uso_1 = registrar_uso_password_inicial(username, db_path)
            uso_2 = registrar_uso_password_inicial(username, db_path)
            cambiar_password_usuario(username, "claveNueva", db_path)
            usuario_actualizado = verificar_usuario(username, "claveNueva", db_path)

        self.assertEqual(username, "aorellana")
        self.assertEqual(usuario["rol"], "basico")
        self.assertTrue(usuario["password_inicial"])
        self.assertEqual(uso_1, 1)
        self.assertEqual(uso_2, 2)
        self.assertFalse(usuario_actualizado["password_inicial"])
        self.assertEqual(usuario_actualizado["usos_password_inicial"], 0)

    def test_auditoria_y_backup(self):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sindicato.db"
            initialize_database(db_path)
            registrar_evento("prueba", "detalle", db_path, "operador")
            backup = crear_backup_automatico(db_path, "test", "admin")
            eventos = listar_eventos_recientes(10, db_path)
            backup_existe = backup.exists()

        self.assertIsNotNone(backup)
        self.assertTrue(backup_existe)
        self.assertEqual(eventos[0]["accion"], "backup")
        self.assertEqual(eventos[0]["usuario"], "admin")
        self.assertEqual(eventos[1]["accion"], "prueba")
        self.assertEqual(eventos[1]["usuario"], "operador")


if __name__ == "__main__":
    unittest.main()
