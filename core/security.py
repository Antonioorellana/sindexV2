from __future__ import annotations

import hashlib
import hmac
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from db.database import DB_PATH, get_connection


HASH_ITERATIONS = 240_000
PASSWORD_KEY = "admin_password_hash"
VALID_ROLES = {"admin", "basico"}
DEFAULT_BASIC_PASSWORD = "1234"


def _hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_hash(password: str, stored_hash: str) -> bool:
    try:
        algoritmo, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _migrar_admin_legacy(connection) -> None:
    usuarios = connection.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if usuarios:
        return
    legacy = connection.execute("SELECT value FROM app_settings WHERE key = ?", (PASSWORD_KEY,)).fetchone()
    if not legacy:
        return
    connection.execute(
        """
        INSERT INTO usuarios (username, password_hash, rol, activo, creado_en)
        VALUES (?, ?, 'admin', 1, ?)
        """,
        ("admin", legacy["value"], _now()),
    )


def usuarios_configurados(db_path=None) -> bool:
    with get_connection(db_path) as connection:
        _migrar_admin_legacy(connection)
        row = connection.execute("SELECT 1 FROM usuarios WHERE activo = 1 LIMIT 1").fetchone()
    return row is not None


def login_configurado(db_path=None) -> bool:
    return usuarios_configurados(db_path)


def crear_usuario(username: str, password: str, rol: str = "basico", db_path=None) -> None:
    username = username.strip().lower()
    rol = rol.strip().lower()
    if not username:
        raise ValueError("El usuario no puede estar vacio")
    if len(password) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres")
    if rol not in VALID_ROLES:
        raise ValueError("Rol invalido")
    password_hash = _hash_password(password)
    usos_password_inicial = 0
    requiere_cambio_password = 0
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO usuarios (
                username, password_hash, rol, activo, usos_password_inicial, requiere_cambio_password, creado_en
            )
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                rol = excluded.rol,
                activo = 1,
                usos_password_inicial = excluded.usos_password_inicial,
                requiere_cambio_password = excluded.requiere_cambio_password
            """,
            (username, password_hash, rol, usos_password_inicial, requiere_cambio_password, _now()),
        )


def generar_username_basico(nombre_completo: str) -> str:
    partes = [p.strip().lower() for p in nombre_completo.split() if p.strip()]
    if len(partes) < 2:
        raise ValueError("Ingresa nombre y apellido")
    return f"{partes[0][0]}{partes[1]}".replace(" ", "")


def crear_usuario_basico(nombre_completo: str, db_path=None) -> str:
    username_base = generar_username_basico(nombre_completo)
    username = username_base
    with get_connection(db_path) as connection:
        contador = 2
        while connection.execute("SELECT 1 FROM usuarios WHERE username = ?", (username,)).fetchone():
            username = f"{username_base}{contador}"
            contador += 1
    crear_usuario(username, DEFAULT_BASIC_PASSWORD, "basico", db_path)
    return username


def guardar_password_admin(password: str, db_path=None) -> None:
    crear_usuario("admin", password, "admin", db_path)


def verificar_usuario(username: str, password: str, db_path=None) -> dict[str, object] | None:
    username = username.strip().lower()
    with get_connection(db_path) as connection:
        _migrar_admin_legacy(connection)
        row = connection.execute(
            """
            SELECT username, password_hash, rol, activo, usos_password_inicial, requiere_cambio_password
            FROM usuarios
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row or int(row["activo"]) != 1:
        return None
    if not _verify_hash(password, row["password_hash"]):
        return None
    return {
        "username": row["username"],
        "rol": row["rol"],
        "activo": int(row["activo"]),
        "usos_password_inicial": int(row["usos_password_inicial"]),
        "requiere_cambio_password": int(row["requiere_cambio_password"]),
        "password_inicial": password == DEFAULT_BASIC_PASSWORD,
    }


def verificar_password_admin(password: str, db_path=None) -> bool:
    usuario = verificar_usuario("admin", password, db_path)
    return bool(usuario and usuario["rol"] == "admin")


def listar_usuarios(db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        _migrar_admin_legacy(connection)
        rows = connection.execute(
            """
            SELECT username, rol, activo, usos_password_inicial, requiere_cambio_password, creado_en
            FROM usuarios
            ORDER BY rol, username
            """
        ).fetchall()
    return [dict(row) for row in rows]


def usuario_existe(username: str, db_path=None) -> bool:
    username = username.strip().lower()
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM usuarios WHERE username = ? AND activo = 1",
            (username,),
        ).fetchone()
    return row is not None


def registrar_uso_password_inicial(username: str, db_path=None) -> int:
    username = username.strip().lower()
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT usos_password_inicial FROM usuarios WHERE username = ?",
            (username,),
        ).fetchone()
        usos = int(row["usos_password_inicial"]) + 1
        connection.execute(
            "UPDATE usuarios SET usos_password_inicial = ? WHERE username = ?",
            (usos, username),
        )
    return usos


def cambiar_password_usuario(username: str, password: str, db_path=None) -> None:
    username = username.strip().lower()
    if len(password) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres")
    if password == DEFAULT_BASIC_PASSWORD:
        raise ValueError("Debes elegir una contraseña distinta de 1234")
    password_hash = _hash_password(password)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE usuarios
            SET password_hash = ?, usos_password_inicial = 0, requiere_cambio_password = 0
            WHERE username = ?
            """,
            (password_hash, username),
        )


def desactivar_usuario(username: str, db_path=None) -> None:
    username = username.strip().lower()
    if username == "admin":
        raise ValueError("No se puede desactivar el usuario admin principal")
    with get_connection(db_path) as connection:
        connection.execute("UPDATE usuarios SET activo = 0 WHERE username = ?", (username,))


def registrar_evento(accion: str, detalle: str = "", db_path=None, usuario: str = "") -> None:
    fecha_hora = _now()
    with get_connection(db_path) as connection:
        connection.execute(
            "INSERT INTO audit_log (fecha_hora, usuario, accion, detalle) VALUES (?, ?, ?, ?)",
            (fecha_hora, usuario, accion, detalle),
        )


def listar_eventos_recientes(limite: int = 50, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT fecha_hora, usuario, accion, detalle
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    return [dict(row) for row in rows]


def crear_backup_automatico(
    db_path: str | Path | None = None,
    motivo: str = "manual",
    usuario: str = "",
) -> Path | None:
    origen = Path(db_path) if db_path else DB_PATH
    if not origen.exists():
        return None
    backup_dir = origen.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = backup_dir / f"sindicato_{motivo}_{timestamp}.db"
    shutil.copy2(origen, destino)
    registrar_evento("backup", f"{motivo}: {destino.name}", origen, usuario)
    return destino
