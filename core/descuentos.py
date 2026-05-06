from __future__ import annotations

from db.database import get_connection


TIPOS_INICIALES = [
    "Capual",
    "Optica",
    "Clinica",
    "Prestamo",
    "Cuota mortuoria",
    "Otro",
]


def inicializar_tipos_descuento(db_path=None) -> None:
    with get_connection(db_path) as connection:
        for nombre in TIPOS_INICIALES:
            connection.execute(
                "INSERT OR IGNORE INTO tipos_descuento (nombre) VALUES (?)",
                (nombre,),
            )


def listar_tipos_descuento(db_path=None) -> list[str]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT nombre FROM tipos_descuento ORDER BY nombre"
        ).fetchall()
    return [row["nombre"] for row in rows]


def agregar_tipo_descuento(nombre: str, db_path=None) -> bool:
    nombre = nombre.strip()
    if not nombre:
        return False
    with get_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM tipos_descuento WHERE LOWER(nombre) = LOWER(?)", (nombre,)
        ).fetchone()
        if existing:
            return False
        connection.execute("INSERT INTO tipos_descuento (nombre) VALUES (?)", (nombre,))
    return True


def guardar_descuento_mensual(
    rut: str, mes: str, tipo: str, monto: int, descripcion: str = "", db_path=None
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO descuentos_mensuales (rut, mes, tipo, monto, descripcion)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rut, mes, tipo, monto, descripcion),
        )


def eliminar_descuento_mensual(descuento_id: int, db_path=None) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            "DELETE FROM descuentos_mensuales WHERE id = ?",
            (descuento_id,),
        )


def obtener_descuentos_socio_mes(rut: str, mes: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, rut, mes, tipo, monto, descripcion
            FROM descuentos_mensuales
            WHERE rut = ? AND mes = ?
            ORDER BY id
            """,
            (rut, mes),
        ).fetchall()
    return [dict(row) for row in rows]


def obtener_descuentos_ultimo_mes_rut(rut: str, db_path=None) -> dict[str, object] | None:
    """Retorna los descuentos del mes más reciente registrado para un RUT."""
    with get_connection(db_path) as connection:
        fila_mes = connection.execute(
            "SELECT mes FROM descuentos_mensuales WHERE rut = ? ORDER BY mes DESC LIMIT 1",
            (rut,),
        ).fetchone()
        if not fila_mes:
            return None
        mes = fila_mes["mes"]
        rows = connection.execute(
            """
            SELECT tipo, monto, descripcion
            FROM descuentos_mensuales
            WHERE rut = ? AND mes = ?
            ORDER BY id
            """,
            (rut, mes),
        ).fetchall()
    descuentos = [dict(row) for row in rows]
    return {
        "mes": mes,
        "descuentos": descuentos,
        "total": sum(int(d["monto"]) for d in descuentos),
    }


def obtener_historial_descuentos_rut(rut: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, mes, tipo, monto, descripcion
            FROM descuentos_mensuales
            WHERE rut = ?
            ORDER BY mes DESC, id
            """,
            (rut,),
        ).fetchall()
    return [dict(row) for row in rows]


def listar_descuentos_mes(mes: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT dm.id, dm.rut,
                   COALESCE(s.nombre, dm.rut) AS nombre,
                   dm.tipo, dm.monto, dm.descripcion
            FROM descuentos_mensuales dm
            LEFT JOIN socios s ON dm.rut = s.rut
            WHERE dm.mes = ?
            ORDER BY COALESCE(s.nombre, dm.rut), dm.tipo, dm.id
            """,
            (mes,),
        ).fetchall()
    return [dict(row) for row in rows]


def obtener_totales_por_rut_mes(mes: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT dm.rut,
                   COALESCE(s.nombre, dm.rut) AS nombre,
                   SUM(dm.monto) AS total
            FROM descuentos_mensuales dm
            LEFT JOIN socios s ON dm.rut = s.rut
            WHERE dm.mes = ?
            GROUP BY dm.rut
            ORDER BY COALESCE(s.nombre, dm.rut)
            """,
            (mes,),
        ).fetchall()
    return [dict(row) for row in rows]


def obtener_resumen_mensual(mes: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT rut, SUM(monto) AS total
            FROM descuentos_mensuales
            WHERE mes = ?
            GROUP BY rut
            ORDER BY rut
            """,
            (mes,),
        ).fetchall()
    return [dict(row) for row in rows]


def cuota_mensual_aplicada(mes: str, db_path=None) -> bool:
    with get_connection(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM descuentos_mensuales WHERE mes = ? AND tipo = 'Cuota mensual'",
            (mes,),
        ).fetchone()[0]
    return count > 0


def aplicar_cuota_mensual_masiva(mes: str, monto: int = 8000, db_path=None) -> int:
    with get_connection(db_path) as connection:
        socios = connection.execute(
            "SELECT rut FROM socios WHERE activo = 1 ORDER BY rut"
        ).fetchall()
        for socio in socios:
            connection.execute(
                """
                INSERT INTO descuentos_mensuales (rut, mes, tipo, monto, descripcion)
                VALUES (?, ?, 'Cuota mensual', ?, '')
                """,
                (socio["rut"], mes, monto),
            )
    return len(socios)


def aplicar_cuota_mortuoria_masiva(mes: str, monto: int, descripcion: str, db_path=None) -> int:
    with get_connection(db_path) as connection:
        socios = connection.execute(
            "SELECT rut FROM socios WHERE activo = 1 ORDER BY rut"
        ).fetchall()
        for socio in socios:
            connection.execute(
                """
                INSERT INTO descuentos_mensuales (rut, mes, tipo, monto, descripcion)
                VALUES (?, ?, ?, ?, ?)
                """,
                (socio["rut"], mes, "Cuota mortuoria", monto, descripcion),
            )
    return len(socios)
