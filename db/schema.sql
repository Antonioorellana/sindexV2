PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS socios (
    rut TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    local TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    mes_carga TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tipos_descuento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS descuentos_mensuales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rut TEXT NOT NULL,
    mes TEXT NOT NULL,
    tipo TEXT NOT NULL,
    monto INTEGER NOT NULL,
    descripcion TEXT DEFAULT '',
    FOREIGN KEY (rut) REFERENCES socios (rut)
);

CREATE TABLE IF NOT EXISTS funs_enviado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes TEXT NOT NULL,
    rut TEXT NOT NULL,
    nombre TEXT NOT NULL,
    motivo TEXT DEFAULT '',
    monto INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cesjun_descuentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes TEXT NOT NULL,
    rut TEXT NOT NULL,
    nombre TEXT NOT NULL,
    monto INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conciliacion_mensual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes TEXT NOT NULL,
    rut TEXT NOT NULL,
    nombre TEXT NOT NULL,
    total_calculado INTEGER NOT NULL,
    total_descontado INTEGER NOT NULL,
    diferencia INTEGER NOT NULL,
    estado TEXT NOT NULL,
    observacion TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('admin', 'basico')),
    activo INTEGER NOT NULL DEFAULT 1,
    usos_password_inicial INTEGER NOT NULL DEFAULT 0,
    requiere_cambio_password INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    usuario TEXT DEFAULT '',
    accion TEXT NOT NULL,
    detalle TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_descuentos_mes ON descuentos_mensuales(mes);
CREATE INDEX IF NOT EXISTS idx_descuentos_rut ON descuentos_mensuales(rut);
CREATE INDEX IF NOT EXISTS idx_funs_mes_rut ON funs_enviado(mes, rut);
CREATE INDEX IF NOT EXISTS idx_cesjun_mes_rut ON cesjun_descuentos(mes, rut);
CREATE INDEX IF NOT EXISTS idx_conciliacion_mes_estado ON conciliacion_mensual(mes, estado);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conciliacion_mes_rut ON conciliacion_mensual(mes, rut);
CREATE INDEX IF NOT EXISTS idx_audit_log_fecha ON audit_log(fecha_hora);
