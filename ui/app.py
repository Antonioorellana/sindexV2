from __future__ import annotations

import os
import platform
from datetime import date
from pathlib import Path

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

from core.conciliacion import (
    cargar_cesjun_desde_registros,
    cargar_funs_enviado_desde_excel,
    conciliar_mes,
    obtener_casos_por_estado,
    obtener_cesjun_ultimo_mes_rut,
    resumen_conciliacion,
)
from core.descuentos import (
    agregar_tipo_descuento,
    eliminar_descuento_mensual,
    guardar_descuento_mensual,
    inicializar_tipos_descuento,
    listar_descuentos_mes,
    listar_tipos_descuento,
    obtener_descuentos_ultimo_mes_rut,
    obtener_historial_descuentos_rut,
    obtener_totales_por_rut_mes,
)
from core.importers import importar_archivo_mensual, importar_sijuan, importar_cesjun
from core.reportes import (
    exportar_descuentos_para_funs,
    exportar_historial_excel,
    exportar_reporte_conciliacion,
    obtener_datos_historial,
    obtener_detalle_conciliacion,
)
from core.ruts import preparar_rut_para_busqueda
from core.security import (
    cambiar_password_usuario,
    crear_backup_automatico,
    crear_usuario,
    crear_usuario_basico,
    desactivar_usuario,
    listar_eventos_recientes,
    listar_usuarios,
    login_configurado,
    registrar_evento,
    registrar_uso_password_inicial,
    usuario_existe,
    verificar_usuario,
)
from core.socios import (
    buscar_socio_por_rut,
    guardar_socios_desde_sijuan,
    listar_socios,
    obtener_resumen_socios,
)
from db.database import DB_PATH, get_connection, initialize_database

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None

DEBUG_UI = os.environ.get("SINDICATO_DEBUG_UI") == "1"
USE_CUSTOMTK = os.environ.get("SINDICATO_USE_CUSTOMTK") == "1"
IS_MAC = platform.system() == "Darwin"
BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVOS_DIR = BASE_DIR / "archivos"
MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _fmt_monto(monto: int) -> str:
    return f"${monto:,}".replace(",", ".")


def _debug(msg: str) -> None:
    if DEBUG_UI:
        print(f"[ui] {msg}")


def buscar_archivo_en_archivos(candidatos: list[str], base_dir: Path = ARCHIVOS_DIR) -> Path | None:
    if not base_dir.exists():
        return None
    wanted = {nombre.lower() for nombre in candidatos}
    for archivo in sorted(base_dir.iterdir()):
        if archivo.is_file() and archivo.name.lower() in wanted:
            return archivo
    return None


def resolver_ruta_archivo(valor_actual: str, candidatos: list[str], base_dir: Path = ARCHIVOS_DIR) -> Path | None:
    actual = Path(valor_actual.strip()) if valor_actual.strip() else None
    if actual and actual.exists():
        return actual
    return buscar_archivo_en_archivos(candidatos, base_dir)


def _parsear_periodo(valor: str) -> tuple[int, int]:
    texto = (valor or "").strip()
    if len(texto) == 7 and texto[4] == "-":
        anio = int(texto[:4])
        mes = int(texto[5:7])
        if 1 <= mes <= 12:
            return anio, mes
    hoy = date.today()
    return hoy.year, hoy.month


class MonthPickerDialog(tk.Toplevel):
    def __init__(self, parent, initial_value: str, on_select):
        super().__init__(parent)
        self.title("Seleccionar mes")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#f4f1eb")
        self._on_select = on_select
        year, _month = _parsear_periodo(initial_value)
        self.year_var = tk.IntVar(value=year)
        container = tk.Frame(self, bg="#ffffff", padx=16, pady=16)
        container.pack(fill="both", expand=True, padx=12, pady=12)
        header = tk.Frame(container, bg="#ffffff")
        header.pack(fill="x")
        tk.Label(header, text="Año", bg="#ffffff", fg="#1f1f1f", font=("Helvetica", 12, "bold")).pack(side="left")
        tk.Spinbox(
            header, from_=2020, to=2100, textvariable=self.year_var, width=8, justify="center",
        ).pack(side="left", padx=(12, 0))
        tk.Label(
            container,
            text="Elige el mes que quieres usar en el sistema.",
            bg="#ffffff", fg="#5f5f5f", font=("Helvetica", 11),
        ).pack(anchor="w", pady=(10, 12))
        grid = tk.Frame(container, bg="#ffffff")
        grid.pack()
        for index, name in enumerate(MONTH_NAMES, start=1):
            button = tk.Button(
                grid, text=name, width=12, relief="flat", bd=0,
                bg="#d7e3dd", fg="#1f1f1f", activebackground="#c5d7cf", activeforeground="#1f1f1f",
                command=lambda m=index: self._select_month(m),
            )
            button.grid(row=(index - 1) // 3, column=(index - 1) % 3, padx=6, pady=6, sticky="ew")
        tk.Button(
            container, text="Cancelar", command=self.destroy, relief="flat", bd=0,
            bg="#6b7280", fg="#ffffff", activebackground="#4b5563", activeforeground="#ffffff",
            padx=12, pady=8,
        ).pack(anchor="e", pady=(14, 0))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent) -> None:
        parent.update_idletasks()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")

    def _select_month(self, month: int) -> None:
        year = int(self.year_var.get())
        self._on_select(f"{year:04d}-{month:02d}")
        self.destroy()


# ── texto builders ──────────────────────────────────────────────────────────

def construir_texto_conciliacion(
    mes: str, resumen: dict[str, object], casos_no_descontados: list[dict[str, object]]
) -> str:
    texto = []
    texto.append(f"Mes conciliado: {mes}")
    texto.append(f"Total enviado FUNS: {_fmt_monto(int(resumen['total_enviado_funs']))}")
    texto.append(f"Total descontado CESJUN: {_fmt_monto(int(resumen['total_descontado_cesjun']))}")
    texto.append(f"Diferencia: {_fmt_monto(int(resumen['diferencia']))}")
    texto.append("")
    texto.append("Estados:")
    for estado, cantidad in resumen["estados"].items():
        texto.append(f"- {estado}: {cantidad}")
    texto.append("")
    if casos_no_descontados:
        texto.append("Casos no descontados:")
        texto.append("-" * 80)
        for caso in casos_no_descontados:
            texto.append(
                f"{caso['rut']} | {caso['nombre']} | "
                f"FUNS: {_fmt_monto(int(caso['total_calculado']))} | "
                f"CESJUN: {_fmt_monto(int(caso['total_descontado']))} | "
                f"Diferencia: {_fmt_monto(int(caso['diferencia']))}"
            )
    else:
        texto.append("No existen casos no descontados.")
    return "\n".join(texto)


def construir_texto_socio(
    socio: dict[str, object] | None,
    desc_mes: dict[str, object] | None = None,
    cesjun_mes: dict[str, object] | None = None,
) -> str:
    if not socio:
        return "No existe un socio cargado en la base de datos para ese RUT."
    lineas = [
        f"RUT: {socio['rut']}",
        f"Nombre: {socio['nombre']}",
        f"Local: {socio['local'] or '(sin local)'}",
        f"Activo: {'Si' if int(socio['activo']) == 1 else 'No'}",
        f"Mes de carga: {socio['mes_carga'] or '(sin dato)'}",
    ]
    # Descuentos que el usuario creó (FUNS a enviar)
    lineas.append("")
    if desc_mes:
        lineas.append(f"Descuentos a solicitar — mes {desc_mes['mes']}:")
        for d in desc_mes["descuentos"]:
            desc = f"  ({d['descripcion']})" if d["descripcion"] else ""
            lineas.append(f"  - {d['tipo']}: {_fmt_monto(int(d['monto']))}{desc}")
        lineas.append(f"  TOTAL a enviar en FUNS: {_fmt_monto(desc_mes['total'])}")
    else:
        lineas.append("Sin descuentos variables creados para este socio.")
    # Lo que efectivamente descontó la empresa (CESJUN)
    lineas.append("")
    if cesjun_mes:
        lineas.append(f"Descontado por empresa (CESJUN) — mes {cesjun_mes['mes']}:")
        for item in cesjun_mes["items"]:
            lineas.append(f"  - {_fmt_monto(int(item['monto']))}")
        lineas.append(f"  TOTAL descontado: {_fmt_monto(cesjun_mes['total'])}")
    else:
        lineas.append("Sin datos CESJUN cargados para este socio.")
    return "\n".join(lineas)


def construir_texto_resumen_socios(resumen: dict[str, object]) -> str:
    lineas = [
        f"Socios totales en base: {resumen['total']}",
        f"Socios activos: {resumen['activos']}",
        f"Ultimo mes cargado: {resumen['ultimo_mes'] or '(sin cargas)'}",
    ]
    top_locales = resumen.get("top_locales", [])
    if top_locales:
        lineas.append("")
        lineas.append("Locales con mas socios activos:")
        for item in top_locales:
            lineas.append(f"- {item['local']}: {item['cantidad']}")
    return "\n".join(lineas)


def construir_texto_reportes(mes: str, resumen: dict[str, object], detalle: list[dict[str, object]]) -> str:
    lineas = [
        f"Mes disponible: {mes}",
        f"Total enviado FUNS: {_fmt_monto(int(resumen['total_enviado_funs']))}",
        f"Total descontado CESJUN: {_fmt_monto(int(resumen['total_descontado_cesjun']))}",
        f"Diferencia: {_fmt_monto(int(resumen['diferencia']))}",
        f"Registros en detalle: {len(detalle)}",
        "",
        "Estados del mes:",
    ]
    for estado, cantidad in resumen["estados"].items():
        lineas.append(f"- {estado}: {cantidad}")
    return "\n".join(lineas)


def construir_texto_descuentos(
    mes: str,
    descuentos: list[dict[str, object]],
    totales: list[dict[str, object]],
) -> str:
    total_monto = sum(int(d["monto"]) for d in descuentos)
    lineas = [
        f"Mes: {mes}",
        f"Descuentos ingresados: {len(descuentos)}",
        f"Personas con descuento: {len(totales)}",
        f"Total a descontar: {_fmt_monto(total_monto)}",
    ]
    if totales:
        lineas.append("")
        lineas.append("Totales por persona (para llenar FUNS):")
        for t in totales:
            lineas.append(f"  {t['rut']}  {t['nombre']}:  {_fmt_monto(int(t['total']))}")
    return "\n".join(lineas)


# ── BaseApp ──────────────────────────────────────────────────────────────────

class BaseApp:
    def __init__(self, master, usuario_actual: dict[str, object] | None = None):
        self.master = master
        self.usuario_actual = usuario_actual or {"username": "admin", "rol": "admin"}
        self.master.title("SindEx")
        self.master.geometry("1280x860")
        self.master.minsize(1120, 760)
        initialize_database()
        inicializar_tipos_descuento(DB_PATH)
        mes_actual = date.today().strftime("%Y-%m")
        # socios tab
        self.ruta_sijuan = tk.StringVar()
        self.mes_sijuan = tk.StringVar(value=mes_actual)
        # buscar tab
        self.rut_busqueda = tk.StringVar()
        # descuentos tab
        self.desc_mes = tk.StringVar(value=mes_actual)
        self.desc_rut = tk.StringVar()
        self.desc_tipo = tk.StringVar()
        self.desc_monto = tk.StringVar()
        self.desc_descripcion = tk.StringVar()
        # conciliar tab
        self.ruta_mensual = tk.StringVar()
        self.ruta_funs = tk.StringVar()
        self.mes = tk.StringVar(value=mes_actual)
        # reportes tab
        self.reporte_mes = tk.StringVar()
        # historial tab
        self.hist_rut = tk.StringVar()
        self.hist_mes = tk.StringVar(value=date.today().strftime("%Y"))
        # seguridad tab
        self.nuevo_usuario = tk.StringVar()
        self.nuevo_usuario_rol = tk.StringVar(value="basico")
        self._build_ui()
        self._autocompletar_archivos()
        self.refrescar_socios()
        self.refrescar_busqueda()
        self.refrescar_descuentos()
        self.refrescar_reportes()
        self.refrescar_historial()
        self.refrescar_configuracion()
        self.refrescar_seguridad()
        self.refrescar_dashboard()

    def _build_ui(self) -> None:
        _debug("build_ui:start")
        wrapper = self._frame(self.master)
        wrapper.pack(fill="both", expand=True)
        self.tabs = self._create_tabs(wrapper)
        self.dashboard_tab = self._add_tab(self.tabs, "Dashboard")
        self.socios_tab = self._add_tab(self.tabs, "Socios")
        self.buscar_tab = self._add_tab(self.tabs, "Buscar RUT")
        self.desc_tab = self._add_tab(self.tabs, "Descuentos")
        self.conciliar_tab = self._add_tab(self.tabs, "Conciliar")
        self.reportes_tab = self._add_tab(self.tabs, "Reportes")
        self.historial_tab = self._add_tab(self.tabs, "Historial")
        self.config_tab = self._add_tab(self.tabs, "Configuración")
        self.seguridad_tab = self._add_tab(self.tabs, "Seguridad") if self.es_admin else None
        self._build_dashboard_tab()
        self._build_socios_tab()
        self._build_buscar_tab()
        self._build_descuentos_tab()
        self._build_conciliar_tab()
        self._build_reportes_tab()
        self._build_historial_tab()
        self._build_configuracion_tab()
        if self.es_admin:
            self._build_seguridad_tab()
        _debug("build_ui:done")

    @property
    def es_admin(self) -> bool:
        return self.usuario_actual.get("rol") == "admin"

    @property
    def username_actual(self) -> str:
        return str(self.usuario_actual.get("username", ""))

    def _registrar(self, accion: str, detalle: str = "") -> None:
        registrar_evento(accion, detalle, DB_PATH, self.username_actual)

    def cerrar_sesion(self) -> None:
        if not messagebox.askyesno("Cerrar sesión", "¿Quieres cerrar la sesión actual?"):
            return
        self._registrar("logout", "sesion cerrada")
        setattr(self.master, "_sindex_logout", True)
        self.master.destroy()

    # ── Dashboard tab ─────────────────────────────────────────────────────────

    def _build_dashboard_tab(self) -> None:
        header = self._frame(self.dashboard_tab)
        header.pack(fill="x", padx=18, pady=(18, 0))
        self._label(header, "Panel ejecutivo").pack(anchor="w")
        self._text_label(
            header,
            "Resumen operativo del padron, conciliacion y casos que requieren revision.",
        ).pack(anchor="w", pady=(6, 0))

        self.dashboard_resumen = self._create_output(self.dashboard_tab, height=10)
        self._pack_output(self.dashboard_resumen, pady=(16, 12))

        acciones = self._frame(self.dashboard_tab)
        acciones.pack(fill="x", padx=12, pady=(0, 12))
        self._button(acciones, "Refrescar panel", command=self.refrescar_dashboard).pack(side="left")
        self._secondary_button(acciones, "Ir a Conciliar", command=lambda: self._show_tab("Conciliar")).pack(side="left", padx=(8, 0))
        self._secondary_button(acciones, "Ver Historial", command=lambda: self._show_tab("Historial")).pack(side="left", padx=(8, 0))

        self.dashboard_tree = self._create_table(
            self.dashboard_tab,
            columns=("estado", "rut", "nombre", "diferencia"),
            headings={"estado": "Estado", "rut": "RUT", "nombre": "Nombre", "diferencia": "Diferencia"},
            heights=12,
        )

    # ── Seguridad tab ─────────────────────────────────────────────────────────

    def _build_seguridad_tab(self) -> None:
        header = self._frame(self.seguridad_tab)
        header.pack(fill="x", padx=18, pady=(18, 0))
        self._label(header, "Seguridad y respaldo").pack(anchor="w")
        self._text_label(
            header,
            "Administracion de usuarios, respaldos de base de datos y registro de actividad sensible.",
        ).pack(anchor="w", pady=(6, 0))

        acciones = self._frame(self.seguridad_tab)
        acciones.pack(fill="x", padx=12, pady=16)
        self._button(acciones, "Crear backup ahora", command=self.crear_backup_manual).pack(side="left")
        self._secondary_button(acciones, "Refrescar actividad", command=self.refrescar_seguridad).pack(side="left", padx=(8, 0))

        usuarios_form = self._frame(self.seguridad_tab)
        usuarios_form.pack(fill="x", padx=12, pady=(0, 12))
        self._label(usuarios_form, "Nombre y apellido").grid(row=0, column=0, sticky="w")
        self._entry(usuarios_form, textvariable=self.nuevo_usuario, width=160).grid(row=0, column=1, sticky="w", padx=(8, 8))
        self._button(usuarios_form, "Crear usuario básico", command=self.crear_usuario_desde_ui).grid(row=0, column=2, sticky="w")
        self._secondary_button(usuarios_form, "Desactivar seleccionado", command=self.desactivar_usuario_seleccionado).grid(row=0, column=3, padx=(8, 0), sticky="w")

        self.seguridad_resumen = self._create_output(self.seguridad_tab, height=5)
        self._pack_output(self.seguridad_resumen, pady=(0, 12))

        self.usuarios_tree = self._create_table(
            self.seguridad_tab,
            columns=("username", "rol", "activo", "usos_password_inicial", "creado_en"),
            headings={
                "username": "Usuario",
                "rol": "Rol",
                "activo": "Activo",
                "usos_password_inicial": "Usos 1234",
                "creado_en": "Creado",
            },
            heights=5,
        )

        self.seguridad_tree = self._create_table(
            self.seguridad_tab,
            columns=("fecha_hora", "usuario", "accion", "detalle"),
            headings={"fecha_hora": "Fecha", "usuario": "Usuario", "accion": "Accion", "detalle": "Detalle"},
            heights=10,
        )

    # ── Configuracion tab ─────────────────────────────────────────────────────

    def _build_configuracion_tab(self) -> None:
        header = self._frame(self.config_tab)
        header.pack(fill="x", padx=18, pady=(18, 0))
        self._label(header, "Configuración de cuenta").pack(anchor="w")
        self._text_label(
            header,
            "Cambia tu contraseña de acceso local. La contraseña inicial 1234 debe reemplazarse después de dos ingresos.",
        ).pack(anchor="w", pady=(6, 0))

        self.config_resumen = self._create_output(self.config_tab, height=5)
        self._pack_output(self.config_resumen, pady=(16, 12))

        acciones = self._frame(self.config_tab)
        acciones.pack(fill="x", padx=12, pady=(0, 12))
        self._button(acciones, "Cambiar mi contraseña", command=self.cambiar_mi_password).pack(side="left")
        self._secondary_button(acciones, "Refrescar", command=self.refrescar_configuracion).pack(side="left", padx=(8, 0))

    # ── Socios tab ────────────────────────────────────────────────────────────

    def _build_socios_tab(self) -> None:
        header = self._frame(self.socios_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Padron de socios").pack(anchor="w")
        self._text_label(
            header,
            "Carga el archivo SIJUAN para actualizar la base. "
            "Tambien puedes cargar el padron desde el archivo mensual en la pestana Conciliar.",
        ).pack(anchor="w", pady=(6, 0))

        form = self._frame(self.socios_tab)
        form.pack(fill="x", padx=12, pady=12)
        self._label(form, "Mes de carga").grid(row=0, column=0, sticky="w")
        self._entry(form, textvariable=self.mes_sijuan, width=120).grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self._secondary_button(form, "Elegir mes", command=lambda: self.abrir_selector_mes(self.mes_sijuan)).grid(row=0, column=4, padx=(8, 0), sticky="ew")
        self._label(form, "Archivo SIJUAN").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._entry(form, textvariable=self.ruta_sijuan).grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        self._button(form, "Seleccionar", command=lambda: self._seleccionar_archivo(self.ruta_sijuan)).grid(row=1, column=2, pady=(10, 0))
        self._secondary_button(form, "Usar carpeta archivos", command=self.autocompletar_sijuan).grid(row=1, column=3, padx=(8, 0), pady=(10, 0), sticky="ew")
        self._button(form, "Cargar padron", command=self.cargar_padron_sijuan).grid(row=0, column=2, sticky="ew")
        self._secondary_button(form, "Refrescar datos", command=self.refrescar_socios).grid(row=0, column=3, padx=(8, 0), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        self.socios_resumen = self._create_output(self.socios_tab, height=7)
        self._pack_output(self.socios_resumen, pady=(0, 12))

        self.socios_tree = self._create_table(
            self.socios_tab,
            columns=("rut", "nombre", "local", "activo", "mes_carga"),
            headings={"rut": "RUT", "nombre": "Nombre", "local": "Local", "activo": "Activo", "mes_carga": "Mes carga"},
            heights=14,
        )

    # ── Buscar RUT tab ────────────────────────────────────────────────────────

    def _build_buscar_tab(self) -> None:
        header = self._frame(self.buscar_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Buscar socio por RUT").pack(anchor="w")
        self._text_label(
            header,
            "Ingresa el RUT en cualquier formato valido. El sistema muestra datos del socio e historial completo de descuentos.",
        ).pack(anchor="w", pady=(6, 0))

        form = self._frame(self.buscar_tab)
        form.pack(fill="x", padx=12, pady=12)
        self._label(form, "RUT").grid(row=0, column=0, sticky="w")
        rut_entry = self._entry(form, textvariable=self.rut_busqueda, width=180)
        rut_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        rut_entry.bind("<Return>", lambda _event: self.buscar_por_rut())
        self._button(form, "Buscar", command=self.buscar_por_rut).grid(row=0, column=2, sticky="w")
        self._secondary_button(form, "Limpiar", command=self.limpiar_busqueda).grid(row=0, column=3, padx=(8, 0), sticky="w")
        self._secondary_button(form, "Ver activos recientes", command=self.refrescar_busqueda).grid(row=0, column=4, padx=(8, 0), sticky="w")

        self.buscar_resultado = self._create_output(self.buscar_tab, height=13)
        self._pack_output(self.buscar_resultado, pady=(0, 6))

        self.buscar_tree = self._create_table(
            self.buscar_tab,
            columns=("rut", "nombre", "local", "mes_carga"),
            headings={"rut": "RUT", "nombre": "Nombre", "local": "Local", "mes_carga": "Mes carga"},
            heights=4,
        )

        hist_header = self._frame(self.buscar_tab)
        hist_header.pack(fill="x", padx=12, pady=(8, 2))
        self._label(hist_header, "Historial de descuentos variables ingresados").pack(anchor="w")

        self.buscar_hist_tree = self._create_table(
            self.buscar_tab,
            columns=("mes", "tipo", "monto", "descripcion"),
            headings={"mes": "Mes", "tipo": "Tipo", "monto": "Monto", "descripcion": "Descripcion"},
            heights=7,
        )

    # ── Descuentos tab ────────────────────────────────────────────────────────

    def _build_descuentos_tab(self) -> None:
        header = self._frame(self.desc_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Descuentos del mes").pack(anchor="w")
        self._text_label(
            header,
            "Crea los descuentos del mes por persona y acreedor. "
            "Aplica la cuota mensual ($8.000) a todos los socios activos o agrega descuentos individuales. "
            "El resumen muestra los totales por persona para completar el FUNS.",
        ).pack(anchor="w", pady=(6, 0))

        form_top = self._frame(self.desc_tab)
        form_top.pack(fill="x", padx=12, pady=(12, 4))
        self._label(form_top, "Mes").grid(row=0, column=0, sticky="w")
        self._entry(form_top, textvariable=self.desc_mes, width=120).grid(row=0, column=1, sticky="w", padx=(8, 8))
        self._secondary_button(
            form_top, "Elegir mes",
            command=lambda: self.abrir_selector_mes_desc(),
        ).grid(row=0, column=2, sticky="w")
        self._secondary_button(form_top, "+ Nuevo tipo de descuento", command=self.agregar_nuevo_tipo).grid(row=0, column=3, padx=(12, 0), sticky="w")
        self._secondary_button(form_top, "Refrescar", command=self.refrescar_descuentos).grid(row=0, column=4, padx=(8, 0), sticky="w")

        form_ind = self._frame(self.desc_tab)
        form_ind.pack(fill="x", padx=12, pady=(4, 4))
        self._label(form_ind, "RUT").grid(row=0, column=0, sticky="w")
        rut_d = self._entry(form_ind, textvariable=self.desc_rut, width=160)
        rut_d.grid(row=0, column=1, sticky="w", padx=(8, 8))
        rut_d.bind("<FocusOut>", lambda _e: self._autocompletar_nombre_desc())
        rut_d.bind("<Return>", lambda _e: self._autocompletar_nombre_desc())
        self._label(form_ind, "Nombre").grid(row=0, column=2, sticky="w")
        self.desc_nombre_var = tk.StringVar()
        self._text_label_var(form_ind, self.desc_nombre_var).grid(row=0, column=3, sticky="w", padx=(8, 0))

        self._label(form_ind, "Tipo").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.desc_tipo_combo = self._combobox(form_ind, textvariable=self.desc_tipo, values=[])
        self.desc_tipo_combo.grid(row=1, column=1, sticky="w", padx=(8, 8), pady=(8, 0))
        self._label(form_ind, "Monto").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self._entry(form_ind, textvariable=self.desc_monto, width=120).grid(row=1, column=3, sticky="w", padx=(8, 8), pady=(8, 0))
        self._button(form_ind, "Agregar descuento", command=self.agregar_descuento_individual).grid(row=1, column=4, padx=(8, 0), pady=(8, 0))

        self._label(form_ind, "Descripcion").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._entry(form_ind, textvariable=self.desc_descripcion).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(8, 8), pady=(8, 0))
        self._secondary_button(form_ind, "Limpiar form", command=self._limpiar_form_desc).grid(row=2, column=4, padx=(8, 0), pady=(8, 0))
        form_ind.grid_columnconfigure(3, weight=1)

        self.desc_resumen = self._create_output(self.desc_tab, height=6)
        self._pack_output(self.desc_resumen, pady=(4, 4))

        det_header = self._frame(self.desc_tab)
        det_header.pack(fill="x", padx=12, pady=(4, 2))
        self._label(det_header, "Detalle de descuentos del mes").pack(side="left", anchor="w")
        self._secondary_button(det_header, "Eliminar seleccionado (Supr)", command=self.eliminar_descuento_seleccionado).pack(side="right")
        self._button(det_header, "Exportar para FUNS", command=self.exportar_desc_funs).pack(side="right", padx=(0, 8))

        self.desc_tree = self._create_table(
            self.desc_tab,
            columns=("rut", "nombre", "tipo", "monto", "descripcion"),
            headings={"rut": "RUT", "nombre": "Nombre", "tipo": "Tipo", "monto": "Monto", "descripcion": "Descripcion"},
            heights=10,
        )
        self.desc_tree.bind("<Delete>", lambda _e: self.eliminar_descuento_seleccionado())

    # ── Conciliar tab ─────────────────────────────────────────────────────────

    def _build_conciliar_tab(self) -> None:
        header = self._frame(self.conciliar_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Conciliacion FUNS vs CESJUN").pack(anchor="w")
        self._text_label(
            header,
            "Carga el archivo mensual (contiene hojas SIJUAN y CESJUN) y el archivo FUNS. "
            "El sistema actualiza el padron, importa lo descontado y compara contra lo enviado.",
        ).pack(anchor="w", pady=(6, 0))

        form = self._frame(self.conciliar_tab)
        form.pack(fill="x", padx=12, pady=12)
        self._label(form, "Mes").grid(row=0, column=0, sticky="w")
        self._entry(form, textvariable=self.mes, width=120).grid(row=0, column=1, sticky="ew", padx=(8, 16))
        self._secondary_button(form, "Elegir mes", command=lambda: self.abrir_selector_mes(self.mes)).grid(row=0, column=4, padx=(8, 0), sticky="ew")

        self._label(form, "Archivo mensual\n(SIJUAN+CESJUN)").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._entry(form, textvariable=self.ruta_mensual).grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        self._button(form, "Seleccionar", command=lambda: self._seleccionar_archivo(self.ruta_mensual)).grid(row=1, column=2, pady=(10, 0))
        self._secondary_button(form, "Auto", command=self.autocompletar_mensual).grid(row=1, column=3, padx=(8, 0), pady=(10, 0), sticky="ew")

        self._label(form, "Archivo FUNS").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._entry(form, textvariable=self.ruta_funs).grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        self._button(form, "Seleccionar", command=lambda: self._seleccionar_archivo(self.ruta_funs)).grid(row=2, column=2, pady=(10, 0))
        self._secondary_button(form, "Auto", command=self.autocompletar_funs).grid(row=2, column=3, padx=(8, 0), pady=(10, 0), sticky="ew")

        self._button(form, "Conciliar", command=self.conciliar_archivos).grid(row=0, column=2, sticky="ew")
        self._secondary_button(form, "Exportar este mes", command=self.exportar_reporte_actual).grid(row=0, column=3, padx=(8, 0), sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        self.conciliar_resumen = self._create_output(self.conciliar_tab, height=9)
        self._pack_output(self.conciliar_resumen, pady=(0, 12))

        self.conciliar_tree = self._create_table(
            self.conciliar_tab,
            columns=("estado", "rut", "nombre", "total_calculado", "total_descontado", "diferencia"),
            headings={
                "estado": "Estado", "rut": "RUT", "nombre": "Nombre",
                "total_calculado": "FUNS", "total_descontado": "CESJUN", "diferencia": "Diferencia",
            },
            heights=12,
        )

    # ── Reportes tab ──────────────────────────────────────────────────────────

    def _build_reportes_tab(self) -> None:
        header = self._frame(self.reportes_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Reportes y meses conciliados").pack(anchor="w")
        self._text_label(
            header,
            "Revisa los meses disponibles en la base y exporta el reporte Excel administrativo de conciliacion.",
        ).pack(anchor="w", pady=(6, 0))

        form = self._frame(self.reportes_tab)
        form.pack(fill="x", padx=12, pady=12)
        self._label(form, "Mes a exportar").grid(row=0, column=0, sticky="w")
        self._entry(form, textvariable=self.reporte_mes, width=120).grid(row=0, column=1, sticky="w", padx=(8, 8))
        self._secondary_button(form, "Elegir mes", command=lambda: self.abrir_selector_mes(self.reporte_mes)).grid(row=0, column=5, padx=(8, 0), sticky="w")
        self._button(form, "Ver resumen", command=self.refrescar_reportes).grid(row=0, column=2, sticky="w")
        self._secondary_button(form, "Usar ultimo mes", command=self.usar_ultimo_mes_conciliado).grid(row=0, column=3, padx=(8, 0), sticky="w")
        self._secondary_button(form, "Exportar Excel", command=self.exportar_reporte_desde_tab).grid(row=0, column=4, padx=(8, 0), sticky="w")

        self.reportes_resumen = self._create_output(self.reportes_tab, height=8)
        self._pack_output(self.reportes_resumen, pady=(0, 12))

        self.reportes_tree = self._create_table(
            self.reportes_tab,
            columns=("estado", "rut", "nombre", "diferencia"),
            headings={"estado": "Estado", "rut": "RUT", "nombre": "Nombre", "diferencia": "Diferencia"},
            heights=13,
        )

    # ── Historial tab ─────────────────────────────────────────────────────────

    def _build_historial_tab(self) -> None:
        header = self._frame(self.historial_tab)
        header.pack(fill="x", padx=12, pady=(12, 0))
        self._label(header, "Historial de descuentos").pack(anchor="w")
        self._text_label(
            header,
            "Vista de matriz con lo efectivamente descontado por empresa desde CESJUN. "
            "Columnas = meses, filas = personas. "
            "Puedes filtrar por RUT y año.",
        ).pack(anchor="w", pady=(6, 0))

        form = self._frame(self.historial_tab)
        form.pack(fill="x", padx=12, pady=(10, 6))
        self._label(form, "RUT").grid(row=0, column=0, sticky="w")
        rut_h = self._entry(form, textvariable=self.hist_rut, width=160)
        rut_h.grid(row=0, column=1, sticky="w", padx=(8, 8))
        rut_h.bind("<Return>", lambda _e: self.refrescar_historial())
        self._label(form, "Año").grid(row=0, column=2, sticky="w")
        mes_h = self._entry(form, textvariable=self.hist_mes, width=120)
        mes_h.grid(row=0, column=3, sticky="w", padx=(8, 8))
        mes_h.bind("<Return>", lambda _e: self.refrescar_historial())
        self._button(form, "Filtrar", command=self.refrescar_historial).grid(row=0, column=5, sticky="w")
        self._secondary_button(form, "Limpiar filtros", command=self._limpiar_filtros_historial).grid(row=0, column=6, padx=(8, 0), sticky="w")
        self._button(form, "Exportar Excel", command=self.exportar_historial).grid(row=0, column=7, padx=(8, 0), sticky="w")

        self.hist_info = self._create_output(self.historial_tab, height=3)
        self._pack_output(self.hist_info, pady=(4, 4))

        # Contenedor que se destruye/recrea al refrescar la matriz
        self.hist_tree_container = self._frame(self.historial_tab)
        self.hist_tree_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.hist_tree = None

    # ── file helpers ──────────────────────────────────────────────────────────

    def _seleccionar_archivo(self, target_var: tk.StringVar) -> None:
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo Excel",
            initialdir=str(ARCHIVOS_DIR) if ARCHIVOS_DIR.exists() else None,
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")],
        )
        if ruta:
            target_var.set(ruta)

    def abrir_selector_mes(self, target_var: tk.StringVar) -> None:
        MonthPickerDialog(self.master, target_var.get(), target_var.set)

    def abrir_selector_mes_desc(self) -> None:
        def on_select(valor: str) -> None:
            self.desc_mes.set(valor)
            self.refrescar_descuentos()
        MonthPickerDialog(self.master, self.desc_mes.get(), on_select)

    def _autocompletar_archivos(self) -> None:
        self.autocompletar_sijuan(silencioso=True)
        self.autocompletar_mensual(silencioso=True)
        self.autocompletar_funs(silencioso=True)

    def autocompletar_sijuan(self, silencioso: bool = False) -> None:
        self._autocompletar_archivo(self.ruta_sijuan, ["SIJUAN.xlsx", "sijuan.xlsx"], "SIJUAN", silencioso)

    def autocompletar_mensual(self, silencioso: bool = False) -> None:
        self._autocompletar_archivo(
            self.ruta_mensual,
            ["MENSUAL.xlsx", "mensual.xlsx", "CESJUN.xlsx", "cesjun.xlsx"],
            "Archivo mensual",
            silencioso,
        )

    def autocompletar_funs(self, silencioso: bool = False) -> None:
        self._autocompletar_archivo(self.ruta_funs, ["FUNS.xlsx", "funs.xlsx"], "FUNS", silencioso)

    def _autocompletar_archivo(
        self, target_var: tk.StringVar, candidatos: list[str], etiqueta: str, silencioso: bool
    ) -> Path | None:
        ruta = resolver_ruta_archivo(target_var.get(), candidatos)
        if ruta:
            target_var.set(str(ruta))
            return ruta
        if not silencioso:
            messagebox.showinfo(
                "Archivo no encontrado",
                f"No encontre {etiqueta} dentro de la carpeta archivos.\n\nSelecciona el archivo manualmente.",
            )
            self._seleccionar_archivo(target_var)
            texto = target_var.get().strip()
            return Path(texto) if texto else None
        return None

    # ── table helpers ─────────────────────────────────────────────────────────

    def _create_table(self, master, columns: tuple[str, ...], headings: dict[str, str], heights: int = 12):
        container = self._frame(master)
        container.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tree = ttk.Treeview(container, columns=columns, show="headings", height=heights)
        for column in columns:
            tree.heading(column, text=headings[column])
            if column == "nombre":
                width = 320
            elif column == "descripcion":
                width = 200
            elif column in ("rut", "mes_carga", "estado", "mes"):
                width = 110
            elif column == "fecha_hora":
                width = 160
            elif column in ("accion", "usuario", "username", "rol", "activo", "usos_password_inicial"):
                width = 130
            elif column == "creado_en":
                width = 160
            elif column in ("local",):
                width = 200
            elif column in ("monto", "total", "total_calculado", "total_descontado", "diferencia"):
                width = 110
            else:
                width = 120
            tree.column(column, width=width, anchor="w")
        scroll_y = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        return tree

    _MONEY_COLS = frozenset(
        ("total_calculado", "total_descontado", "diferencia", "monto", "total")
    )

    def _fill_tree(self, tree, rows: list[dict[str, object]], columns: tuple[str, ...]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            values = []
            for column in columns:
                valor = row.get(column, "")
                if column in self._MONEY_COLS and valor not in ("", None):
                    valor = _fmt_monto(int(valor))
                elif column == "activo":
                    valor = "Si" if int(valor) == 1 else "No"
                values.append(valor)
            row_id = str(row["id"]) if "id" in row else ""
            if row_id:
                try:
                    tree.insert("", "end", iid=row_id, values=values)
                except tk.TclError:
                    tree.insert("", "end", values=values)
            else:
                tree.insert("", "end", values=values)

    def _set_output_text(self, widget, texto: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", texto)

    def _pack_output(self, widget, pady=(0, 12)) -> None:
        widget.pack(fill="x", expand=False, padx=12, pady=pady)

    def _listar_meses_conciliados(self) -> list[str]:
        with get_connection(DB_PATH) as connection:
            rows = connection.execute(
                "SELECT DISTINCT mes FROM conciliacion_mensual WHERE COALESCE(mes, '') <> '' ORDER BY mes DESC"
            ).fetchall()
        return [row["mes"] for row in rows]

    def refrescar_dashboard(self) -> None:
        if not hasattr(self, "dashboard_resumen"):
            return
        resumen_socios = obtener_resumen_socios(DB_PATH)
        meses = self._listar_meses_conciliados()
        mes = meses[0] if meses else ""
        if mes:
            resumen = resumen_conciliacion(mes, DB_PATH)
            detalle = obtener_detalle_conciliacion(mes, DB_PATH)
            observables = [fila for fila in detalle if fila["estado"] != "ok"]
            estados = resumen["estados"]
            total_funs = int(resumen["total_enviado_funs"])
            total_cesjun = int(resumen["total_descontado_cesjun"])
            diferencia = int(resumen["diferencia"])
        else:
            observables = []
            estados = {}
            total_funs = total_cesjun = diferencia = 0

        lineas = [
            "Estado general",
            f"Socios activos: {resumen_socios['activos']} de {resumen_socios['total']} registrados",
            f"Ultimo padron cargado: {resumen_socios['ultimo_mes'] or '(sin cargas)'}",
            f"Ultimo mes conciliado: {mes or '(sin conciliaciones)'}",
            "",
            "Conciliacion",
            f"Total FUNS enviado: {_fmt_monto(total_funs)}",
            f"Total CESJUN descontado: {_fmt_monto(total_cesjun)}",
            f"Diferencia total: {_fmt_monto(diferencia)}",
            f"Estados: ok={estados.get('ok', 0)} | diferencia={estados.get('diferencia', 0)} | no descontado={estados.get('no_descontado', 0)} | inesperado={estados.get('inesperado', 0)}",
            "",
            "Casos que requieren revision" if observables else "Sin casos pendientes en el ultimo mes conciliado.",
        ]
        self._set_output_text(self.dashboard_resumen, "\n".join(lineas))
        self._fill_tree(self.dashboard_tree, observables[:80], ("estado", "rut", "nombre", "diferencia"))

    # ── Socios actions ────────────────────────────────────────────────────────

    def cargar_padron_sijuan(self) -> None:
        mes_carga = self.mes_sijuan.get().strip()
        ruta = self._autocompletar_archivo(self.ruta_sijuan, ["SIJUAN.xlsx", "sijuan.xlsx"], "SIJUAN", silencioso=True)
        if not ruta:
            ruta = self._autocompletar_archivo(self.ruta_sijuan, ["SIJUAN.xlsx", "sijuan.xlsx"], "SIJUAN", silencioso=False)
        if not mes_carga or not ruta or not ruta.exists():
            messagebox.showerror("Datos incompletos", "Debes indicar el mes de carga y disponer del archivo SIJUAN.")
            return
        try:
            crear_backup_automatico(DB_PATH, "antes_padron", self.username_actual)
            # Intentar cargar como archivo mensual (puede tener SIJUAN + CESJUN)
            datos = importar_archivo_mensual(ruta)
            socios = datos["socios"]
            cesjun_registros = datos["cesjun"]
            resultado = guardar_socios_desde_sijuan(socios, mes_carga, DB_PATH)
            # Si el archivo también tiene CESJUN, cargarlo automáticamente
            cesjun_cargados = 0
            if cesjun_registros:
                cargar_cesjun_desde_registros(cesjun_registros, mes_carga, DB_PATH)
                cesjun_cargados = len(cesjun_registros)
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error al cargar SIJUAN", str(exc))
            return
        self.refrescar_socios()
        self.refrescar_busqueda()
        self.refrescar_historial()
        self.refrescar_seguridad()
        self.refrescar_dashboard()
        self._registrar(
            "carga_padron",
            f"mes={mes_carga}; socios={len(socios)}; cesjun={cesjun_cargados}",
        )
        resumen_lineas = [
            f"Socios procesados: {len(socios)}",
            f"Actualizados: {resultado['actualizados']}",
            f"Duplicados omitidos: {resultado['duplicados_omitidos']}",
            f"Activos del mes: {resultado['socios_activos']}",
        ]
        if cesjun_cargados:
            resumen_lineas.append(f"Registros CESJUN cargados: {cesjun_cargados}")
        messagebox.showinfo("Carga completada", "\n".join(resumen_lineas))

    def refrescar_socios(self) -> None:
        resumen = obtener_resumen_socios(DB_PATH)
        activos = listar_socios(activo=True, limite=300, db_path=DB_PATH)
        self._set_output_text(self.socios_resumen, construir_texto_resumen_socios(resumen))
        self._fill_tree(self.socios_tree, activos, ("rut", "nombre", "local", "activo", "mes_carga"))

    # ── Buscar actions ────────────────────────────────────────────────────────

    def buscar_por_rut(self) -> None:
        rut_ingresado = self.rut_busqueda.get().strip()
        if not rut_ingresado:
            messagebox.showerror("Falta RUT", "Ingresa un RUT para buscar.")
            return
        try:
            rut_normalizado = preparar_rut_para_busqueda(rut_ingresado)
        except ValueError as exc:
            messagebox.showerror("RUT invalido", str(exc))
            return
        self.rut_busqueda.set(rut_normalizado)
        socio = buscar_socio_por_rut(rut_normalizado, DB_PATH)
        self._registrar("buscar_rut", f"rut={rut_normalizado}; encontrado={'si' if socio else 'no'}")
        desc_mes = obtener_descuentos_ultimo_mes_rut(rut_normalizado, DB_PATH)
        cesjun_mes = obtener_cesjun_ultimo_mes_rut(rut_normalizado, DB_PATH)
        self._set_output_text(self.buscar_resultado, construir_texto_socio(socio, desc_mes, cesjun_mes))
        if socio:
            self._fill_tree(self.buscar_tree, [socio], ("rut", "nombre", "local", "mes_carga"))
        else:
            self.refrescar_busqueda()
        historial = obtener_historial_descuentos_rut(rut_normalizado, DB_PATH)
        self._fill_tree(self.buscar_hist_tree, historial, ("mes", "tipo", "monto", "descripcion"))

    def limpiar_busqueda(self) -> None:
        self.rut_busqueda.set("")
        self._fill_tree(self.buscar_hist_tree, [], ("mes", "tipo", "monto", "descripcion"))
        self.refrescar_busqueda()

    def refrescar_busqueda(self) -> None:
        activos = listar_socios(activo=True, limite=80, db_path=DB_PATH)
        self._set_output_text(
            self.buscar_resultado,
            "Resultados de busqueda por RUT.\n\nDebajo se muestran socios activos recientes.",
        )
        self._fill_tree(self.buscar_tree, activos, ("rut", "nombre", "local", "mes_carga"))

    # ── Descuentos actions ────────────────────────────────────────────────────

    def refrescar_descuentos(self) -> None:
        mes = self.desc_mes.get().strip()
        tipos = listar_tipos_descuento(DB_PATH)
        self._update_combobox_values(self.desc_tipo_combo, tipos)
        if tipos and not self.desc_tipo.get():
            self.desc_tipo.set(tipos[0])
        if not mes:
            self._set_output_text(self.desc_resumen, "Selecciona un mes para ver los descuentos.")
            self._fill_tree(self.desc_tree, [], ("rut", "nombre", "tipo", "monto", "descripcion"))
            return
        descuentos = listar_descuentos_mes(mes, DB_PATH)
        totales = obtener_totales_por_rut_mes(mes, DB_PATH)
        self._set_output_text(self.desc_resumen, construir_texto_descuentos(mes, descuentos, totales))
        self._fill_tree(self.desc_tree, descuentos, ("rut", "nombre", "tipo", "monto", "descripcion"))

    def agregar_descuento_individual(self) -> None:
        rut_raw = self.desc_rut.get().strip()
        tipo = self.desc_tipo.get().strip()
        monto_raw = self.desc_monto.get().strip()
        mes = self.desc_mes.get().strip()
        descripcion = self.desc_descripcion.get().strip()

        if not mes:
            messagebox.showerror("Mes faltante", "Selecciona un mes primero.")
            return
        if not rut_raw:
            messagebox.showerror("RUT faltante", "Ingresa el RUT del socio.")
            return
        if not tipo:
            messagebox.showerror("Tipo faltante", "Selecciona el tipo de descuento.")
            return
        if not monto_raw:
            messagebox.showerror("Monto faltante", "Ingresa el monto del descuento.")
            return

        try:
            rut = preparar_rut_para_busqueda(rut_raw)
        except ValueError as exc:
            messagebox.showerror("RUT invalido", str(exc))
            return
        try:
            monto_str = monto_raw.replace(".", "").replace(",", "").replace("$", "")
            monto = int(monto_str)
            if monto <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Monto invalido", "El monto debe ser un numero entero positivo.")
            return

        try:
            guardar_descuento_mensual(rut, mes, tipo, monto, descripcion, DB_PATH)
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error al guardar", str(exc))
            return

        self._limpiar_form_desc()
        self.refrescar_descuentos()
        self.refrescar_dashboard()
        self._registrar("agregar_descuento", f"mes={mes}; rut={rut}; tipo={tipo}; monto={monto}")

    def eliminar_descuento_seleccionado(self) -> None:
        selected = self.desc_tree.selection()
        if not selected:
            messagebox.showinfo("Sin seleccion", "Selecciona un descuento de la tabla para eliminar.")
            return
        if not messagebox.askyesno("Confirmar", "¿Eliminar el descuento seleccionado?"):
            return
        try:
            db_id = int(selected[0])
        except ValueError:
            return
        eliminar_descuento_mensual(db_id, DB_PATH)
        self.refrescar_descuentos()
        self.refrescar_dashboard()
        self._registrar("eliminar_descuento", f"id={db_id}")

    def agregar_nuevo_tipo(self) -> None:
        nombre = simpledialog.askstring(
            "Nuevo tipo de descuento",
            "Nombre del nuevo tipo (ej: Gimnasio, Farmacia, Gas):",
            parent=self.master,
        )
        if not nombre:
            return
        if agregar_tipo_descuento(nombre, DB_PATH):
            self.refrescar_descuentos()
            self._registrar("agregar_tipo_descuento", f"tipo={nombre}")
            messagebox.showinfo("Tipo agregado", f"Tipo '{nombre}' agregado correctamente.")
        else:
            messagebox.showinfo("Ya existe", f"El tipo '{nombre}' ya existe.")

    def _autocompletar_nombre_desc(self) -> None:
        rut_raw = self.desc_rut.get().strip()
        if not rut_raw:
            self.desc_nombre_var.set("")
            return
        try:
            rut = preparar_rut_para_busqueda(rut_raw)
            self.desc_rut.set(rut)
        except ValueError:
            self.desc_nombre_var.set("RUT invalido")
            return
        socio = buscar_socio_por_rut(rut, DB_PATH)
        self.desc_nombre_var.set(socio["nombre"] if socio else "(no encontrado en padron)")

    def _limpiar_form_desc(self) -> None:
        self.desc_rut.set("")
        self.desc_monto.set("")
        self.desc_descripcion.set("")
        self.desc_nombre_var.set("")

    # ── Conciliar actions ─────────────────────────────────────────────────────

    def conciliar_archivos(self) -> None:
        mes = self.mes.get().strip()
        ruta_mensual = self._autocompletar_archivo(
            self.ruta_mensual,
            ["MENSUAL.xlsx", "mensual.xlsx", "CESJUN.xlsx", "cesjun.xlsx"],
            "Archivo mensual",
            silencioso=True,
        )
        ruta_funs = self._autocompletar_archivo(self.ruta_funs, ["FUNS.xlsx", "funs.xlsx"], "FUNS", silencioso=True)
        if not ruta_mensual:
            ruta_mensual = self._autocompletar_archivo(
                self.ruta_mensual,
                ["MENSUAL.xlsx", "mensual.xlsx", "CESJUN.xlsx", "cesjun.xlsx"],
                "Archivo mensual",
                silencioso=False,
            )
        if not ruta_funs:
            ruta_funs = self._autocompletar_archivo(self.ruta_funs, ["FUNS.xlsx", "funs.xlsx"], "FUNS", silencioso=False)
        if not mes or not ruta_mensual or not ruta_funs or not ruta_mensual.exists() or not ruta_funs.exists():
            messagebox.showerror("Datos incompletos", "Debes ingresar un mes, el archivo mensual y el archivo FUNS.")
            return
        try:
            crear_backup_automatico(DB_PATH, "antes_conciliar", self.username_actual)
            datos = importar_archivo_mensual(ruta_mensual)
            if datos["socios"]:
                guardar_socios_desde_sijuan(datos["socios"], mes, DB_PATH)
            cargar_cesjun_desde_registros(datos["cesjun"], mes, DB_PATH)
            cargar_funs_enviado_desde_excel(ruta_funs, mes, DB_PATH)
            conciliar_mes(mes, DB_PATH)
            resumen = resumen_conciliacion(mes, DB_PATH)
            no_descontados = obtener_casos_por_estado(mes, "no_descontado", DB_PATH)
            detalle = obtener_detalle_conciliacion(mes, DB_PATH)
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error de conciliacion", str(exc))
            return
        self.reporte_mes.set(mes)
        self._set_output_text(self.conciliar_resumen, construir_texto_conciliacion(mes, resumen, no_descontados))
        observables = [fila for fila in detalle if fila["estado"] != "ok"]
        if not observables:
            observables = detalle[:100]
        self._fill_tree(
            self.conciliar_tree,
            observables,
            ("estado", "rut", "nombre", "total_calculado", "total_descontado", "diferencia"),
        )
        self.refrescar_socios()
        self.refrescar_reportes()
        self.refrescar_historial()
        self.refrescar_seguridad()
        self.refrescar_dashboard()
        self._registrar("conciliacion", f"mes={mes}; casos={len(detalle)}")

    def usar_ultimo_mes_conciliado(self) -> None:
        meses = self._listar_meses_conciliados()
        if not meses:
            messagebox.showerror("Sin datos", "Todavia no existen meses conciliados en la base.")
            return
        self.reporte_mes.set(meses[0])
        self.refrescar_reportes()

    def refrescar_reportes(self) -> None:
        meses = self._listar_meses_conciliados()
        if not self.reporte_mes.get().strip() and meses:
            self.reporte_mes.set(meses[0])
        mes = self.reporte_mes.get().strip()
        if not mes:
            self._set_output_text(
                self.reportes_resumen,
                "Todavia no hay conciliaciones guardadas.\n\n"
                "Cuando concilies un mes, aqui aparecera el resumen y el acceso a exportar Excel.",
            )
            self._fill_tree(self.reportes_tree, [], ("estado", "rut", "nombre", "diferencia"))
            return
        try:
            resumen = resumen_conciliacion(mes, DB_PATH)
            detalle = obtener_detalle_conciliacion(mes, DB_PATH)
        except Exception:
            self._set_output_text(self.reportes_resumen, f"No hay datos de conciliacion para el mes {mes}.")
            self._fill_tree(self.reportes_tree, [], ("estado", "rut", "nombre", "diferencia"))
            return
        self._set_output_text(self.reportes_resumen, construir_texto_reportes(mes, resumen, detalle))
        observables = [fila for fila in detalle if fila["estado"] != "ok"]
        if not observables:
            observables = detalle[:100]
        self._fill_tree(self.reportes_tree, observables, ("estado", "rut", "nombre", "diferencia"))

    def exportar_reporte_actual(self) -> None:
        mes = self.mes.get().strip()
        if not mes:
            messagebox.showerror("Mes faltante", "Primero indica el mes conciliado.")
            return
        self._exportar_reporte(mes)

    def exportar_reporte_desde_tab(self) -> None:
        mes = self.reporte_mes.get().strip()
        if not mes:
            messagebox.showerror("Mes faltante", "Indica el mes que quieres exportar.")
            return
        self._exportar_reporte(mes)

    def _exportar_reporte(self, mes: str) -> None:
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte de conciliacion",
            defaultextension=".xlsx",
            initialfile=f"reporte_conciliacion_{mes}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not ruta:
            return
        try:
            destino = exportar_reporte_conciliacion(mes, ruta, DB_PATH)
            self._registrar("exportar_reporte", f"mes={mes}; archivo={Path(destino).name}")
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error al exportar", str(exc))
            return
        messagebox.showinfo("Reporte exportado", f"Reporte generado en:\n{destino}")

    # ── Exportar descuentos (FUNS helper) ────────────────────────────────────

    def exportar_desc_funs(self) -> None:
        mes = self.desc_mes.get().strip()
        if not mes:
            messagebox.showerror("Mes faltante", "Selecciona un mes primero.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar descuentos para FUNS",
            defaultextension=".xlsx",
            initialfile=f"descuentos_funs_{mes}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not ruta:
            return
        try:
            destino = exportar_descuentos_para_funs(mes, ruta, DB_PATH)
            self._registrar("exportar_funs", f"mes={mes}; archivo={Path(destino).name}")
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error al exportar", str(exc))
            return
        messagebox.showinfo("Exportado", f"Archivo generado en:\n{destino}")

    # ── Historial actions ─────────────────────────────────────────────────────

    def _limpiar_filtros_historial(self) -> None:
        self.hist_rut.set("")
        self.hist_mes.set(date.today().strftime("%Y"))
        self.refrescar_historial()

    def refrescar_historial(self) -> None:
        rut_raw = self.hist_rut.get().strip()
        anio_raw = self.hist_mes.get().strip() or date.today().strftime("%Y")
        rut_filtro = None
        try:
            anio = int(anio_raw)
            if anio < 2000 or anio > 2100:
                raise ValueError
            self.hist_mes.set(str(anio))
        except ValueError:
            messagebox.showerror("Año invalido", "Ingresa un año valido, por ejemplo 2026.")
            return
        if rut_raw:
            try:
                from core.ruts import preparar_rut_para_busqueda
                rut_filtro = preparar_rut_para_busqueda(rut_raw)
                self.hist_rut.set(rut_filtro)
            except ValueError:
                messagebox.showerror("RUT invalido", "El RUT ingresado no es valido.")
                return
        try:
            meses, filas = obtener_datos_historial(DB_PATH, rut_filtro, anio)
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error", str(exc))
            return

        n_personas = len(filas)
        n_meses = len(meses)
        problemas = sum(1 for f in filas if f.get("_problema"))
        info_lines = [
            f"Año: {anio}  |  Personas: {n_personas}  |  Meses: {n_meses}  |  Con diferencias/no descontados: {problemas}",
        ]
        if not filas:
            info_lines.append("No hay descuentos registrados para los filtros indicados.")
        self._set_output_text(self.hist_info, "\n".join(info_lines))
        self._rebuild_hist_tree(meses, filas)

    def _rebuild_hist_tree(self, meses: list[str], filas: list[dict]) -> None:
        # Destruir widgets anteriores en el contenedor
        for widget in self.hist_tree_container.winfo_children():
            widget.destroy()

        columns = ("rut", "nombre") + tuple(meses)
        tree = ttk.Treeview(self.hist_tree_container, columns=columns, show="headings", height=18)

        # Encabezados y anchos
        tree.heading("rut", text="RUT")
        tree.column("rut", width=130, anchor="w", stretch=False)
        tree.heading("nombre", text="Nombre")
        tree.column("nombre", width=280, anchor="w")
        for mes in meses:
            try:
                month_idx = int(mes[-2:]) - 1
                heading = MONTH_NAMES[month_idx]
            except (ValueError, IndexError):
                heading = mes
            tree.heading(mes, text=heading)
            tree.column(mes, width=110, anchor="e", stretch=False)

        # Colores para fila "problema"
        tree.tag_configure("problema", foreground="#cc0000", background="#fff0f0")
        tree.tag_configure("normal", foreground="#1f1f1f", background="#ffffff")

        scroll_y = ttk.Scrollbar(self.hist_tree_container, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(self.hist_tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.hist_tree_container.grid_rowconfigure(0, weight=1)
        self.hist_tree_container.grid_columnconfigure(0, weight=1)

        # Llenar filas
        for fila in filas:
            values = [fila.get("rut", ""), fila.get("nombre", "")]
            for mes in meses:
                total = fila.get(mes)
                values.append(_fmt_monto(total) if total is not None else "sin descuento")
            tag = "problema" if fila.get("_problema") else "normal"
            tree.insert("", "end", values=values, tags=(tag,))

        self.hist_tree = tree

    def exportar_historial(self) -> None:
        rut_raw = self.hist_rut.get().strip()
        anio_raw = self.hist_mes.get().strip() or date.today().strftime("%Y")
        rut_filtro = None
        try:
            anio = int(anio_raw)
            if anio < 2000 or anio > 2100:
                raise ValueError
        except ValueError:
            messagebox.showerror("Año invalido", "Ingresa un año valido, por ejemplo 2026.")
            return
        if rut_raw:
            try:
                rut_filtro = preparar_rut_para_busqueda(rut_raw)
            except ValueError:
                messagebox.showerror("RUT invalido", "El RUT ingresado no es valido.")
                return
        ruta = filedialog.asksaveasfilename(
            title="Guardar historial",
            defaultextension=".xlsx",
            initialfile=f"historial_descuentos_{anio}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not ruta:
            return
        try:
            destino = exportar_historial_excel(ruta, DB_PATH, rut_filtro, anio)
            self._registrar("exportar_historial", f"anio={anio}; archivo={Path(destino).name}")
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error al exportar", str(exc))
            return
        messagebox.showinfo("Exportado", f"Historial generado en:\n{destino}")

    # ── Seguridad actions ─────────────────────────────────────────────────────

    def crear_backup_manual(self) -> None:
        try:
            destino = crear_backup_automatico(DB_PATH, "manual", self.username_actual)
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error de backup", str(exc))
            return
        self.refrescar_seguridad()
        if destino:
            messagebox.showinfo("Backup creado", f"Respaldo generado en:\n{destino}")
        else:
            messagebox.showinfo("Backup no creado", "Todavia no existe base de datos para respaldar.")

    def refrescar_seguridad(self) -> None:
        if not hasattr(self, "seguridad_resumen"):
            return
        eventos = listar_eventos_recientes(80, DB_PATH)
        usuarios = listar_usuarios(DB_PATH)
        backup_dir = DB_PATH.parent / "backups"
        backups = sorted(backup_dir.glob("*.db"), reverse=True) if backup_dir.exists() else []
        lineas = [
            f"Sesion actual: {self.username_actual} ({self.usuario_actual.get('rol')})",
            "Acceso local: protegido por usuario y contraseña",
            f"Base de datos: {DB_PATH}",
            f"Usuarios activos: {sum(1 for u in usuarios if int(u['activo']) == 1)}",
            f"Backups disponibles: {len(backups)}",
            f"Ultimo backup: {backups[0].name if backups else '(sin backups)'}",
        ]
        self._set_output_text(self.seguridad_resumen, "\n".join(lineas))
        self._fill_tree(self.usuarios_tree, usuarios, ("username", "rol", "activo", "usos_password_inicial", "creado_en"))
        self._fill_tree(self.seguridad_tree, eventos, ("fecha_hora", "usuario", "accion", "detalle"))

    def crear_usuario_desde_ui(self) -> None:
        nombre_completo = self.nuevo_usuario.get().strip()
        if not nombre_completo:
            messagebox.showerror("Nombre faltante", "Ingresa nombre y apellido.")
            return
        try:
            username = crear_usuario_basico(nombre_completo, DB_PATH)
        except Exception as exc:
            messagebox.showerror("Error al crear usuario", str(exc))
            return
        self._registrar("usuario_guardado", f"usuario={username}; rol=basico; password_inicial=1234")
        self.nuevo_usuario.set("")
        self.refrescar_seguridad()
        messagebox.showinfo(
            "Usuario guardado",
            f"Usuario creado: {username}\nContraseña inicial: 1234\nDebe cambiarla al tercer ingreso.",
        )

    def desactivar_usuario_seleccionado(self) -> None:
        selected = self.usuarios_tree.selection()
        if not selected:
            messagebox.showinfo("Sin seleccion", "Selecciona un usuario de la tabla.")
            return
        values = self.usuarios_tree.item(selected[0], "values")
        username = values[0] if values else ""
        if not username:
            return
        if not messagebox.askyesno("Confirmar", f"¿Desactivar el usuario {username}?"):
            return
        try:
            desactivar_usuario(username, DB_PATH)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._registrar("usuario_desactivado", f"usuario={username}")
        self.refrescar_seguridad()

    def refrescar_configuracion(self) -> None:
        if not hasattr(self, "config_resumen"):
            return
        lineas = [
            f"Usuario: {self.username_actual}",
            f"Rol: {self.usuario_actual.get('rol')}",
            f"Usos de contraseña inicial 1234: {self.usuario_actual.get('usos_password_inicial', 0)}",
            "Puedes cambiar tu contraseña en cualquier momento.",
        ]
        self._set_output_text(self.config_resumen, "\n".join(lineas))

    def cambiar_mi_password(self) -> bool:
        actual = simpledialog.askstring("Contraseña actual", "Ingresa tu contraseña actual:", show="*", parent=self.master)
        if actual is None:
            return False
        if not verificar_usuario(self.username_actual, actual, DB_PATH):
            messagebox.showerror("Contraseña incorrecta", "La contraseña actual no es correcta.")
            return False
        nueva = simpledialog.askstring("Nueva contraseña", "Nueva contraseña:", show="*", parent=self.master)
        if nueva is None:
            return False
        confirmar = simpledialog.askstring("Confirmar", "Repite la nueva contraseña:", show="*", parent=self.master)
        if confirmar is None:
            return False
        if nueva != confirmar:
            messagebox.showerror("No coincide", "Las contraseñas no coinciden.")
            return False
        try:
            cambiar_password_usuario(self.username_actual, nueva, DB_PATH)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return False
        self.usuario_actual["usos_password_inicial"] = 0
        self.usuario_actual["requiere_cambio_password"] = 0
        self.usuario_actual["password_inicial"] = False
        self._registrar("cambio_password", "contraseña actualizada")
        self.refrescar_configuracion()
        if self.es_admin:
            self.refrescar_seguridad()
        messagebox.showinfo("Contraseña actualizada", "Tu contraseña fue cambiada correctamente.")
        return True

    # ── abstract widget factory ───────────────────────────────────────────────

    def _frame(self, master):
        raise NotImplementedError

    def _create_tabs(self, master):
        raise NotImplementedError

    def _add_tab(self, tabs, title: str):
        raise NotImplementedError

    def _label(self, master, text: str):
        raise NotImplementedError

    def _entry(self, master, **kwargs):
        raise NotImplementedError

    def _button(self, master, text: str, command):
        raise NotImplementedError

    def _secondary_button(self, master, text: str, command):
        raise NotImplementedError

    def _text_label(self, master, text: str):
        raise NotImplementedError

    def _text_label_var(self, master, textvariable):
        raise NotImplementedError

    def _create_output(self, master, height: int = 6):
        raise NotImplementedError

    def _combobox(self, master, textvariable=None, values=None):
        raise NotImplementedError

    def _update_combobox_values(self, combobox, values: list[str]) -> None:
        raise NotImplementedError


# ── TkFallbackApp ─────────────────────────────────────────────────────────────

class TkFallbackApp(BaseApp):
    BG = "#eef2f4"
    PANEL = "#ffffff"
    TEXT = "#172126"
    MUTED = "#64727a"
    ACCENT = "#146052"
    ACCENT_DARK = "#0f3f3a"
    SIDEBAR = "#102a3a"
    SIDEBAR_MUTED = "#9fb4bf"
    LINE = "#d8e0e4"
    SOFT = "#edf6f3"

    def __init__(self, master, usuario_actual: dict[str, object] | None = None):
        master.configure(bg=self.BG)
        self._configure_styles(master)
        self._tab_frames = {}
        self._tab_buttons = {}
        self._content_host = None
        super().__init__(master, usuario_actual)

    def _configure_styles(self, master) -> None:
        style = ttk.Style(master)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Treeview",
            background="#ffffff",
            foreground=self.TEXT,
            fieldbackground="#ffffff",
            bordercolor=self.LINE,
            borderwidth=0,
            rowheight=28,
            font=("Helvetica", 11),
        )
        style.configure(
            "Treeview.Heading",
            background="#e6eef1",
            foreground=self.TEXT,
            relief="flat",
            font=("Helvetica", 11, "bold"),
        )
        style.map("Treeview", background=[("selected", "#cfe8df")], foreground=[("selected", self.TEXT)])

    def _frame(self, master):
        return tk.Frame(master, bg=self.PANEL)

    def _create_tabs(self, master):
        tabs = tk.Frame(master, bg=self.BG)
        tabs.pack(fill="both", expand=True)
        sidebar = tk.Frame(tabs, bg=self.SIDEBAR, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=self.SIDEBAR)
        brand.pack(fill="x", padx=18, pady=(22, 18))
        tk.Label(
            brand,
            text="SindEx",
            bg=self.SIDEBAR,
            fg="#ffffff",
            justify="left",
            font=("Helvetica", 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="Control mensual seguro",
            bg=self.SIDEBAR,
            fg=self.SIDEBAR_MUTED,
            justify="left",
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(8, 0))
        self._buttons_host = tk.Frame(sidebar, bg=self.SIDEBAR)
        self._buttons_host.pack(fill="x", padx=12, pady=(10, 0))
        footer = tk.Frame(sidebar, bg=self.SIDEBAR)
        footer.pack(side="bottom", fill="x", padx=18, pady=18)
        tk.Label(
            footer,
            text=f"Sesion: {self.username_actual}\nDesarrollado por\nOrveDevs 2026",
            bg=self.SIDEBAR,
            fg=self.SIDEBAR_MUTED,
            justify="left",
            font=("Helvetica", 10),
        ).pack(anchor="w")
        tk.Button(
            footer,
            text="Cerrar sesión",
            command=self.cerrar_sesion,
            bg="#17384c",
            fg="#ffffff",
            activebackground="#0f2735",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=("Helvetica", 10, "bold"),
        ).pack(fill="x", pady=(12, 0))
        self._content_host = tk.Frame(tabs, bg=self.BG)
        self._content_host.pack(side="left", fill="both", expand=True, padx=18, pady=18)
        return tabs

    def _add_tab(self, tabs, title: str):
        tab = tk.Frame(self._content_host, bg=self.PANEL, highlightbackground=self.LINE, highlightthickness=1)
        button = tk.Button(
            self._buttons_host,
            text=title,
            anchor="w",
            relief="flat",
            bd=0,
            padx=14,
            pady=11,
            bg=self.SIDEBAR,
            fg=self.SIDEBAR_MUTED,
            activebackground="#17384c",
            activeforeground="#ffffff",
            font=("Helvetica", 12, "bold" if title == "Dashboard" else "normal"),
            command=lambda name=title: self._show_tab(name),
        )
        button.pack(fill="x", pady=3)
        self._tab_frames[title] = tab
        self._tab_buttons[title] = button
        if len(self._tab_frames) == 1:
            self._show_tab(title)
        return tab

    def _show_tab(self, title: str) -> None:
        for name, frame in self._tab_frames.items():
            if name == title:
                frame.pack(fill="both", expand=True)
                self._tab_buttons[name].configure(bg=self.ACCENT, fg="#ffffff")
            else:
                frame.pack_forget()
                self._tab_buttons[name].configure(bg=self.SIDEBAR, fg=self.SIDEBAR_MUTED)

    def _label(self, master, text: str):
        return tk.Label(master, text=text, bg=self.PANEL, fg=self.TEXT, font=("Helvetica", 17, "bold"))

    def _entry(self, master, **kwargs):
        width = kwargs.pop("width", None)
        entry = tk.Entry(
            master,
            **kwargs,
            bg="#ffffff",
            fg=self.TEXT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=self.LINE,
            highlightcolor=self.ACCENT,
            insertbackground=self.TEXT,
            font=("Helvetica", 11),
        )
        if width is not None:
            entry.configure(width=max(int(width / 10), 12))
        return entry

    def _button(self, master, text: str, command):
        return tk.Button(
            master,
            text=text,
            command=command,
            bg=self.ACCENT,
            fg="#ffffff",
            activebackground=self.ACCENT_DARK,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=9,
            font=("Helvetica", 11, "bold"),
        )

    def _secondary_button(self, master, text: str, command):
        return tk.Button(
            master,
            text=text,
            command=command,
            bg=self.SOFT,
            fg=self.ACCENT_DARK,
            activebackground="#d9ece6",
            activeforeground=self.ACCENT_DARK,
            relief="flat",
            bd=0,
            padx=14,
            pady=9,
            font=("Helvetica", 11),
        )

    def _text_label(self, master, text: str):
        return tk.Label(
            master, text=text, wraplength=960, justify="left",
            bg=self.PANEL, fg=self.MUTED, font=("Helvetica", 12),
        )

    def _text_label_var(self, master, textvariable):
        return tk.Label(
            master, textvariable=textvariable, bg=self.PANEL, fg=self.MUTED, font=("Helvetica", 12),
        )

    def _create_output(self, master, height: int = 6):
        return tk.Text(
            master, wrap="word", height=height, bg="#fcfbf8", fg=self.TEXT,
            relief="solid", bd=1, highlightthickness=1, highlightbackground=self.LINE,
            insertbackground=self.TEXT, font=("Helvetica", 11), padx=10, pady=8,
        )

    def _combobox(self, master, textvariable=None, values=None):
        return ttk.Combobox(master, textvariable=textvariable, values=values or [], state="readonly", width=22)

    def _update_combobox_values(self, combobox, values: list[str]) -> None:
        combobox["values"] = values
        if values and not combobox.get():
            combobox.set(values[0])


# ── CustomTkApp ───────────────────────────────────────────────────────────────

class CustomTkApp(BaseApp):
    def __init__(self, usuario_actual: dict[str, object] | None = None):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        _debug("customtk:init")
        super().__init__(ctk.CTk(), usuario_actual)

    def _frame(self, master):
        return ctk.CTkFrame(master)

    def _create_tabs(self, master):
        tabs = ctk.CTkTabview(master)
        tabs.pack(fill="both", expand=True)
        return tabs

    def _add_tab(self, tabs, title: str):
        tabs.add(title)
        return tabs.tab(title)

    def _show_tab(self, title: str) -> None:
        self.tabs.set(title)

    def _label(self, master, text: str):
        return ctk.CTkLabel(master, text=text)

    def _entry(self, master, **kwargs):
        width = kwargs.pop("width", 400)
        return ctk.CTkEntry(master, width=width, **kwargs)

    def _button(self, master, text: str, command):
        return ctk.CTkButton(master, text=text, command=command)

    def _secondary_button(self, master, text: str, command):
        return ctk.CTkButton(master, text=text, command=command, fg_color="#6b7280", hover_color="#4b5563")

    def _text_label(self, master, text: str):
        return ctk.CTkLabel(master, text=text, justify="left", wraplength=960)

    def _text_label_var(self, master, textvariable):
        return ctk.CTkLabel(master, textvariable=textvariable, justify="left")

    def _create_output(self, master, height: int = 6):
        textbox = ctk.CTkTextbox(master)
        textbox.configure(height=max(height * 24, 120))
        return textbox

    def _combobox(self, master, textvariable=None, values=None):
        return ctk.CTkComboBox(master, variable=textvariable, values=values or [])

    def _update_combobox_values(self, combobox, values: list[str]) -> None:
        combobox.configure(values=values)
        if values and not combobox.get():
            combobox.set(values[0])


# ── entry point ───────────────────────────────────────────────────────────────

def _pedir_login(root) -> dict[str, object] | None:
    initialize_database()
    root.title("SindEx - Acceso")
    root.geometry("460x380")
    root.minsize(460, 380)
    root.resizable(False, False)
    root.update_idletasks()
    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
        root.after(500, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass
    if not login_configurado(DB_PATH):
        messagebox.showinfo(
            "Configurar acceso",
            "SindEx necesita crear el usuario administrador inicial para proteger los datos.",
            parent=root,
        )
        while True:
            password = simpledialog.askstring("Crear contraseña", "Nueva contraseña:", show="*", parent=root)
            if password is None:
                return None
            confirmacion = simpledialog.askstring("Confirmar contraseña", "Repite la contraseña:", show="*", parent=root)
            if confirmacion is None:
                return None
            if len(password) < 6:
                messagebox.showerror("Contraseña debil", "Usa al menos 6 caracteres.", parent=root)
                continue
            if password != confirmacion:
                messagebox.showerror("No coincide", "Las contraseñas no coinciden.", parent=root)
                continue
            try:
                crear_usuario("admin", password, "admin", DB_PATH)
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=root)
                continue
            usuario = verificar_usuario("admin", password, DB_PATH)
            registrar_evento("seguridad", "usuario administrador inicial configurado", DB_PATH, "admin")
            return usuario

    for widget in root.winfo_children():
        widget.destroy()

    resultado: dict[str, object] = {"usuario": None}
    intentos = tk.IntVar(value=0)
    terminado = tk.BooleanVar(value=False)

    root.configure(bg="#eef2f4")
    panel = tk.Frame(root, bg="#ffffff", highlightbackground="#d8e0e4", highlightthickness=1)
    panel.pack(fill="both", expand=True, padx=22, pady=22)
    tk.Label(panel, text="SindEx", bg="#ffffff", fg="#102a3a", font=("Helvetica", 24, "bold")).pack(anchor="w", padx=22, pady=(20, 0))
    tk.Label(panel, text="Ingresa con tu usuario y contraseña", bg="#ffffff", fg="#64727a", font=("Helvetica", 11)).pack(anchor="w", padx=22, pady=(4, 14))

    form = tk.Frame(panel, bg="#ffffff")
    form.pack(fill="x", padx=22)
    tk.Label(form, text="Usuario", bg="#ffffff", fg="#172126", font=("Helvetica", 11, "bold")).grid(row=0, column=0, sticky="w")
    username_var = tk.StringVar()
    username_entry = tk.Entry(form, textvariable=username_var, bg="#ffffff", fg="#172126", relief="solid", bd=1)
    username_entry.grid(row=1, column=0, sticky="ew", pady=(4, 10))
    tk.Label(form, text="Contraseña", bg="#ffffff", fg="#172126", font=("Helvetica", 11, "bold")).grid(row=2, column=0, sticky="w")
    password_var = tk.StringVar()
    password_entry = tk.Entry(form, textvariable=password_var, show="*", bg="#ffffff", fg="#172126", relief="solid", bd=1)
    password_entry.grid(row=3, column=0, sticky="ew", pady=(4, 0))
    form.grid_columnconfigure(0, weight=1)

    status_var = tk.StringVar(value="")
    status_label = tk.Label(panel, textvariable=status_var, bg="#ffffff", fg="#9a3412", font=("Helvetica", 10), height=2, anchor="w", justify="left")
    status_label.pack(fill="x", padx=22, pady=(8, 0))

    buttons = tk.Frame(panel, bg="#ffffff")
    buttons.pack(fill="x", padx=22, pady=(8, 20))

    def crear_usuario_login() -> None:
        nombre_completo = simpledialog.askstring(
            "Nuevo usuario básico",
            "Nombre y apellido (ej: Antonio Orellana):",
            parent=root,
        )
        if not nombre_completo:
            return
        try:
            nuevo_usuario = crear_usuario_basico(nombre_completo, DB_PATH)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=root)
            return
        registrar_evento("usuario_auto_creado", f"usuario={nuevo_usuario}; password_inicial=1234", DB_PATH, nuevo_usuario)
        username_var.set(nuevo_usuario)
        password_var.set("1234")
        messagebox.showinfo("Usuario creado", f"Usuario: {nuevo_usuario}\nContraseña inicial: 1234", parent=root)

    def ingresar() -> None:
        username = username_var.get().strip().lower()
        password = password_var.get()
        if not username or not password:
            status_var.set("Ingresa usuario y contraseña.")
            return
        if not usuario_existe(username, DB_PATH):
            status_var.set("Usuario no existe. Usa Crear usuario básico.")
            return
        usuario = verificar_usuario(username, password, DB_PATH)
        if usuario:
            if usuario.get("rol") == "basico" and usuario.get("password_inicial"):
                usos = int(usuario.get("usos_password_inicial", 0))
                if usos >= 2:
                    messagebox.showwarning(
                        "Cambio obligatorio",
                        "La contraseña inicial 1234 ya fue usada dos veces. Debes cambiarla para continuar.",
                        parent=root,
                    )
                    usuario_actualizado = _cambiar_password_en_login(root, str(usuario["username"]))
                    if not usuario_actualizado:
                        return
                    registrar_evento("login_ok", f"rol={usuario_actualizado['rol']}; password_actualizada=si", DB_PATH, str(usuario_actualizado["username"]))
                    resultado["usuario"] = usuario_actualizado
                    terminado.set(True)
                    return
                nuevos_usos = registrar_uso_password_inicial(str(usuario["username"]), DB_PATH)
                usuario["usos_password_inicial"] = nuevos_usos
                if nuevos_usos == 2:
                    messagebox.showinfo(
                        "Aviso de seguridad",
                        "Esta fue tu segunda entrada con 1234. En el próximo ingreso deberás cambiar la contraseña.",
                        parent=root,
                    )
            registrar_evento("login_ok", f"rol={usuario['rol']}", DB_PATH, str(usuario["username"]))
            resultado["usuario"] = usuario
            terminado.set(True)
            return
        intentos.set(intentos.get() + 1)
        restantes = 3 - intentos.get()
        if restantes:
            status_var.set(f"Contraseña incorrecta. Intentos restantes: {restantes}")
            password_var.set("")
            password_entry.focus_set()
            return
        registrar_evento("login_bloqueado", "3 intentos fallidos", DB_PATH, username)
        messagebox.showerror("Acceso bloqueado", "Demasiados intentos fallidos.", parent=root)
        terminado.set(True)

    def salir() -> None:
        registrar_evento("login_cancelado", "usuario salio desde login", DB_PATH)
        terminado.set(True)

    tk.Button(buttons, text="Ingresar", command=ingresar, bg="#146052", fg="#ffffff", relief="flat", padx=14, pady=9, font=("Helvetica", 11, "bold")).pack(side="left")
    tk.Button(buttons, text="Crear usuario básico", command=crear_usuario_login, bg="#edf6f3", fg="#0f3f3a", relief="flat", padx=14, pady=9, font=("Helvetica", 11)).pack(side="left", padx=(8, 0))
    tk.Button(buttons, text="Salir", command=salir, bg="#e5e7eb", fg="#172126", relief="flat", padx=14, pady=9, font=("Helvetica", 11)).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", salir)
    root.bind("<Return>", lambda _event: ingresar())
    username_entry.focus_set()
    root.wait_variable(terminado)
    for widget in root.winfo_children():
        widget.destroy()
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    return resultado["usuario"]


def _cambiar_password_en_login(root, username: str) -> dict[str, object] | None:
    while True:
        nueva = simpledialog.askstring("Nueva contraseña", "Nueva contraseña:", show="*", parent=root)
        if nueva is None:
            return None
        confirmar = simpledialog.askstring("Confirmar contraseña", "Repite la nueva contraseña:", show="*", parent=root)
        if confirmar is None:
            return None
        if nueva != confirmar:
            messagebox.showerror("No coincide", "Las contraseñas no coinciden.", parent=root)
            continue
        try:
            cambiar_password_usuario(username, nueva, DB_PATH)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=root)
            continue
        registrar_evento("cambio_password_obligatorio", "contraseña inicial reemplazada", DB_PATH, username)
        messagebox.showinfo(
            "Contraseña actualizada",
            "Contraseña cambiada. Entrarás con tu nueva contraseña.",
            parent=root,
        )
        return verificar_usuario(username, nueva, DB_PATH)


def run() -> None:
    if IS_MAC or ctk is None or not USE_CUSTOMTK:
        while True:
            root = tk.Tk()
            usuario = _pedir_login(root)
            if not usuario:
                root.destroy()
                return
            app = TkFallbackApp(root, usuario)
            app.master.mainloop()
            if getattr(root, "_sindex_logout", False):
                continue
            return
        return
    while True:
        login_root = tk.Tk()
        usuario = _pedir_login(login_root)
        if not usuario:
            login_root.destroy()
            return
        login_root.destroy()
        app = CustomTkApp(usuario)
        app.master.mainloop()
        if getattr(app.master, "_sindex_logout", False):
            continue
        return
