from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from core.importers import importar_cesjun, importar_funs_enviado
from db.database import get_connection


def cargar_funs_enviado_desde_excel(ruta_archivo: str | Path, mes: str, db_path=None) -> dict[str, int]:
    registros = importar_funs_enviado(ruta_archivo)
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM funs_enviado WHERE mes = ?", (mes,))
        for registro in registros:
            connection.execute(
                """
                INSERT INTO funs_enviado (mes, rut, nombre, motivo, monto)
                VALUES (?, ?, ?, ?, ?)
                """,
                (mes, registro["rut"], registro["nombre"], registro["motivo"], registro["monto"]),
            )
    return {
        "registros_leidos": len(registros),
        "registros_guardados": len(registros),
        "registros_rechazados": 0,
        "total_enviado_funs": sum(int(registro["monto"]) for registro in registros),
    }


def cargar_cesjun_desde_excel(ruta_archivo: str | Path, mes: str, db_path=None) -> dict[str, int]:
    registros = importar_cesjun(ruta_archivo)
    return cargar_cesjun_desde_registros(registros, mes, db_path)


def cargar_cesjun_desde_registros(registros: list[dict[str, object]], mes: str, db_path=None) -> dict[str, int]:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM cesjun_descuentos WHERE mes = ?", (mes,))
        for registro in registros:
            connection.execute(
                """
                INSERT INTO cesjun_descuentos (mes, rut, nombre, monto)
                VALUES (?, ?, ?, ?)
                """,
                (mes, registro["rut"], registro["nombre"], registro["monto"]),
            )
    return {
        "registros_leidos": len(registros),
        "registros_guardados": len(registros),
        "registros_rechazados": 0,
        "total_descontado_cesjun": sum(int(registro["monto"]) for registro in registros),
    }


def _obtener_nombres_por_rut(connection, mes: str) -> dict[str, str]:
    nombres: dict[str, str] = {}
    for tabla in ("socios", "funs_enviado", "cesjun_descuentos"):
        if tabla == "socios":
            query = "SELECT rut, nombre FROM socios ORDER BY activo DESC"
            params = ()
        else:
            query = f"SELECT rut, nombre FROM {tabla} WHERE mes = ?"
            params = (mes,)
        for row in connection.execute(query, params):
            nombres.setdefault(row["rut"], row["nombre"])
    return nombres


def conciliar_mes(mes: str, db_path=None) -> dict[str, int]:
    with get_connection(db_path) as connection:
        funs = defaultdict(int)
        cesjun = defaultdict(int)
        for row in connection.execute("SELECT rut, monto FROM funs_enviado WHERE mes = ?", (mes,)):
            funs[row["rut"]] += int(row["monto"])
        for row in connection.execute("SELECT rut, monto FROM cesjun_descuentos WHERE mes = ?", (mes,)):
            cesjun[row["rut"]] += int(row["monto"])
        nombres = _obtener_nombres_por_rut(connection, mes)
        connection.execute("DELETE FROM conciliacion_mensual WHERE mes = ?", (mes,))
        total_casos = 0
        for rut in sorted(set(funs) | set(cesjun)):
            total_enviado = funs.get(rut, 0)
            total_descontado = cesjun.get(rut, 0)
            diferencia = total_enviado - total_descontado
            if rut in funs and rut in cesjun:
                estado = "ok" if diferencia == 0 else "diferencia"
            elif rut in funs:
                estado = "no_descontado"
            else:
                estado = "inesperado"
            connection.execute(
                """
                INSERT INTO conciliacion_mensual (
                    mes, rut, nombre, total_calculado, total_descontado, diferencia, estado, observacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mes,
                    rut,
                    nombres.get(rut, ""),
                    total_enviado,
                    total_descontado,
                    diferencia,
                    estado,
                    "",
                ),
            )
            total_casos += 1
    return {"casos_conciliados": total_casos}


def resumen_conciliacion(mes: str, db_path=None) -> dict[str, object]:
    with get_connection(db_path) as connection:
        total_row = connection.execute(
            """
            SELECT
                COALESCE(SUM(total_calculado), 0) AS total_enviado_funs,
                COALESCE(SUM(total_descontado), 0) AS total_descontado_cesjun,
                COALESCE(SUM(diferencia), 0) AS diferencia_total
            FROM conciliacion_mensual
            WHERE mes = ?
            """,
            (mes,),
        ).fetchone()
        estados = dict(
            connection.execute(
                """
                SELECT estado, COUNT(*) AS cantidad
                FROM conciliacion_mensual
                WHERE mes = ?
                GROUP BY estado
                ORDER BY estado
                """,
                (mes,),
            ).fetchall()
        )
    return {
        "mes": mes,
        "total_enviado_funs": int(total_row["total_enviado_funs"]),
        "total_descontado_cesjun": int(total_row["total_descontado_cesjun"]),
        "diferencia": int(total_row["diferencia_total"]),
        "estados": {estado: int(cantidad) for estado, cantidad in estados.items()},
    }


def obtener_casos_por_estado(mes: str, estado: str, db_path=None) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT rut, nombre, total_calculado, total_descontado, diferencia, estado, observacion
            FROM conciliacion_mensual
            WHERE mes = ? AND estado = ?
            ORDER BY rut
            """,
            (mes, estado),
        ).fetchall()
    return [dict(row) for row in rows]


def obtener_nombre_para_rut(rut: str, mes: str, db_path=None) -> str:
    with get_connection(db_path) as connection:
        nombres = _obtener_nombres_por_rut(connection, mes)
    return nombres.get(rut, "")


def obtener_cesjun_ultimo_mes_rut(rut: str, db_path=None) -> dict[str, object] | None:
    """Retorna los descuentos CESJUN del mes más reciente para un RUT."""
    with get_connection(db_path) as connection:
        fila_mes = connection.execute(
            "SELECT mes FROM cesjun_descuentos WHERE rut = ? ORDER BY mes DESC LIMIT 1",
            (rut,),
        ).fetchone()
        if not fila_mes:
            return None
        mes = fila_mes["mes"]
        rows = connection.execute(
            "SELECT monto FROM cesjun_descuentos WHERE rut = ? AND mes = ? ORDER BY rowid",
            (rut, mes),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {
        "mes": mes,
        "items": items,
        "total": sum(int(i["monto"]) for i in items),
    }

