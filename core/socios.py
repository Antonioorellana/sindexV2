from __future__ import annotations

from db.database import get_connection


def guardar_socios_desde_sijuan(socios: list[dict[str, object]], mes_carga: str, db_path=None) -> dict[str, int]:
    actualizados = 0
    duplicados = 0
    vistos: set[str] = set()
    with get_connection(db_path) as connection:
        connection.execute("UPDATE socios SET activo = 0")
        for socio in socios:
            rut = str(socio["rut"])
            if rut in vistos:
                duplicados += 1
                continue
            vistos.add(rut)
            existente = connection.execute("SELECT rut FROM socios WHERE rut = ?", (rut,)).fetchone()
            connection.execute(
                """
                INSERT INTO socios (rut, nombre, local, activo, mes_carga)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(rut) DO UPDATE SET
                    nombre = excluded.nombre,
                    local = excluded.local,
                    activo = 1,
                    mes_carga = excluded.mes_carga
                """,
                (rut, socio["nombre"], socio.get("local", ""), mes_carga),
            )
            if existente:
                actualizados += 1
    return {"actualizados": actualizados, "duplicados_omitidos": duplicados, "socios_activos": len(vistos)}


def buscar_socio_por_rut(rut: str, db_path=None):
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT rut, nombre, local, activo, mes_carga FROM socios WHERE rut = ?",
            (rut,),
        ).fetchone()
    return dict(row) if row else None


def listar_socios(activo: bool | None = None, limite: int = 200, db_path=None) -> list[dict[str, object]]:
    query = "SELECT rut, nombre, local, activo, mes_carga FROM socios"
    params: tuple[object, ...] = ()
    if activo is not None:
        query += " WHERE activo = ?"
        params = (1 if activo else 0,)
    query += " ORDER BY nombre LIMIT ?"
    params = params + (limite,)
    with get_connection(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def obtener_resumen_socios(db_path=None) -> dict[str, object]:
    with get_connection(db_path) as connection:
        totales = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END), 0) AS activos,
                COALESCE(MAX(mes_carga), '') AS ultimo_mes
            FROM socios
            """
        ).fetchone()
        locales = connection.execute(
            """
            SELECT local, COUNT(*) AS cantidad
            FROM socios
            WHERE activo = 1 AND COALESCE(local, '') <> ''
            GROUP BY local
            ORDER BY cantidad DESC, local ASC
            LIMIT 5
            """
        ).fetchall()
    return {
        "total": int(totales["total"]),
        "activos": int(totales["activos"]),
        "ultimo_mes": totales["ultimo_mes"] or "",
        "top_locales": [dict(row) for row in locales],
    }
