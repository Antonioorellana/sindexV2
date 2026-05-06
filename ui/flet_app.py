from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import flet as ft

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
from core.importers import importar_archivo_mensual
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
from core.socios import buscar_socio_por_rut, guardar_socios_desde_sijuan, listar_socios, obtener_resumen_socios
from db.database import DB_PATH, get_connection, initialize_database


MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


class C:
    bg = "#F4F0E9"
    card = "#FFFFFF"
    sidebar = "#063A40"
    active = "#0F5C63"
    accent = "#006064"
    accent_dark = "#003F43"
    text = "#14252B"
    muted = "#687A7D"
    line = "#E5DED4"
    mint = "#DDF6EC"
    mint_text = "#0D6B50"
    amber = "#FFF0C2"
    amber_text = "#8A5A00"
    red = "#FFE1DE"
    red_text = "#A13B32"


def _icon(name: str):
    source = getattr(ft, "Icons", None) or getattr(ft, "icons", None)
    return getattr(source, name, None) if source else None


def _today_month() -> str:
    return date.today().strftime("%Y-%m")


def _today_year() -> str:
    return date.today().strftime("%Y")


def _opening_datetime() -> str:
    return datetime.now().strftime("%d-%m-%Y %H:%M")


def _money(value: object) -> str:
    if value is None:
        return "sin descuento"
    return f"${int(value):,}".replace(",", ".")


def _parse_month(value: str) -> str:
    text = (value or "").strip()
    if len(text) != 7 or text[4] != "-":
        raise ValueError("Ingresa el mes con formato AAAA-MM.")
    year = int(text[:4])
    month = int(text[5:])
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise ValueError("Ingresa un mes valido, por ejemplo 2026-05.")
    return f"{year:04d}-{month:02d}"


def _parse_money(value: str) -> int:
    amount = int((value or "").replace("$", "").replace(".", "").replace(",", "").strip())
    if amount <= 0:
        raise ValueError
    return amount


def _months_with_conciliation() -> list[str]:
    with get_connection(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT DISTINCT mes FROM conciliacion_mensual WHERE COALESCE(mes, '') <> '' ORDER BY mes DESC"
        ).fetchall()
    return [row["mes"] for row in rows]


def field(label: str, value: str = "", width: int | None = None, password: bool = False) -> ft.TextField:
    return ft.TextField(
        label=label,
        value=value,
        password=password,
        can_reveal_password=password,
        width=width,
        height=52,
        dense=True,
        border_radius=6,
        border_color=C.line,
        focused_border_color=C.accent,
        text_size=13,
        color=C.text,
        label_style=ft.TextStyle(size=12, color=C.muted),
    )


def primary(text: str, click=None, icon=None) -> ft.FilledButton:
    return ft.FilledButton(
        content=text,
        icon=icon,
        on_click=click,
        style=ft.ButtonStyle(
            bgcolor=C.accent,
            color="#FFFFFF",
            shape=ft.RoundedRectangleBorder(radius=6),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
        ),
    )


def secondary(text: str, click=None, icon=None) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        content=text,
        icon=icon,
        on_click=click,
        style=ft.ButtonStyle(
            color=C.accent_dark,
            side=ft.BorderSide(1, C.line),
            shape=ft.RoundedRectangleBorder(radius=6),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
        ),
    )


def sidebar_button(text: str, click=None, icon=None) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        content=text,
        icon=icon,
        on_click=click,
        style=ft.ButtonStyle(
            color="#FFFFFF",
            side=ft.BorderSide(1, "#A9C5C8"),
            shape=ft.RoundedRectangleBorder(radius=6),
            padding=ft.padding.symmetric(horizontal=12, vertical=11),
        ),
    )


def card(content: ft.Control, expand: bool | int = False, padding: int = 16) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=C.card,
        border=ft.border.all(1, C.line),
        border_radius=8,
        padding=padding,
        expand=expand,
        shadow=ft.BoxShadow(blur_radius=14, color="#18000000", offset=ft.Offset(0, 4)),
    )


def metric(title: str, value: str, note: str = "", tone: str = "ok") -> ft.Container:
    bg = C.mint if tone == "ok" else C.amber if tone == "warn" else C.red
    fg = C.mint_text if tone == "ok" else C.amber_text if tone == "warn" else C.red_text
    return card(
        ft.Column(
            [
                ft.Text(title, size=11, color=C.muted, weight=ft.FontWeight.W_600),
                ft.Text(value, size=21, color=C.text, weight=ft.FontWeight.BOLD),
                ft.Container(ft.Text(note or " ", size=10, color=fg), bgcolor=bg, border_radius=10, padding=ft.padding.symmetric(horizontal=8, vertical=3)),
            ],
            spacing=6,
        ),
        expand=True,
        padding=14,
    )


def chip(text: str) -> ft.Container:
    tone = "ok" if text == "ok" else "warn" if text in ("diferencia", "inesperado") else "bad"
    bg = C.mint if tone == "ok" else C.amber if tone == "warn" else C.red
    fg = C.mint_text if tone == "ok" else C.amber_text if tone == "warn" else C.red_text
    return ft.Container(ft.Text(text or "-", size=11, color=fg, weight=ft.FontWeight.W_600), bgcolor=bg, border_radius=12, padding=ft.padding.symmetric(horizontal=10, vertical=3))


def table(headers: list[str], rows: list[list[object]], expand: bool = True) -> ft.Container:
    data_rows = []
    for row in rows:
        cells = [ft.DataCell(value if isinstance(value, ft.Control) else ft.Text(str(value), size=12, color=C.text)) for value in row]
        data_rows.append(ft.DataRow(cells=cells))
    return ft.Container(
        ft.Row(
            [
                ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(h, size=11, weight=ft.FontWeight.BOLD, color=C.muted)) for h in headers],
                    rows=data_rows,
                    heading_row_color="#F3EEE7",
                    data_row_min_height=38,
                    data_row_max_height=44,
                    column_spacing=18,
                    horizontal_lines=ft.BorderSide(1, "#F0E8DE"),
                )
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=expand,
    )


class SindExFlet:
    def __init__(self, page: ft.Page):
        self.page = page
        self.user: dict[str, object] | None = None
        self.view = "dashboard"
        self.selected_discount_id: int | None = None
        self.selected_username = ""
        self.file_target = ""
        self.save_action = ""
        self.export_data: dict[str, object] = {}
        self.show_create_login = False
        self.opened_at = _opening_datetime()
        self.file_picker = ft.FilePicker()
        self.save_picker = ft.FilePicker()
        self.page.services.extend([self.file_picker, self.save_picker])
        initialize_database()
        inicializar_tipos_descuento(DB_PATH)
        self._build_state()
        self._setup_page()
        self.login_screen()

    def _build_state(self) -> None:
        month = _today_month()
        self.login_user = field("Usuario")
        self.login_password = field("Contraseña", password=True)
        self.admin_password = field("Contraseña admin", password=True)
        self.admin_confirm = field("Confirmar contraseña", password=True)
        self.new_login_name = field("Nombre y apellido")
        self.socios_month = field("Mes de carga", month, 150)
        self.socios_file = field("Archivo SIJUAN / mensual")
        self.search_rut = field("RUT", width=260)
        self.desc_month = field("Mes", month, 140)
        self.desc_rut = field("RUT", width=180)
        self.desc_type = ft.Dropdown(label="Tipo", width=220, border_color=C.line, focused_border_color=C.accent)
        self.desc_amount = field("Monto", width=160)
        self.desc_description = field("Descripcion")
        self.new_type = field("Nuevo tipo", width=220)
        self.conc_month = field("Mes", month, 140)
        self.conc_monthly_file = field("Planilla mensual / CESJUN")
        self.conc_funs_file = field("Archivo FUNS")
        self.report_month = field("Mes", "", 140)
        self.history_rut = field("RUT", width=220)
        self.history_year = field("Año", _today_year(), 120)
        self.current_password = field("Contraseña actual", password=True)
        self.new_password = field("Nueva contraseña", password=True)
        self.confirm_password = field("Confirmar nueva contraseña", password=True)
        self.security_name = field("Nombre y apellido", width=300)

    def _setup_page(self) -> None:
        self.page.title = "SindEx"
        self.page.bgcolor = C.bg
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 1320
        self.page.window_height = 860
        self.page.window_min_width = 1060
        self.page.window_min_height = 720
        self.page.padding = 0

    @property
    def username(self) -> str:
        return str((self.user or {}).get("username", ""))

    @property
    def is_admin(self) -> bool:
        return (self.user or {}).get("rol") == "admin"

    def log(self, action: str, detail: str = "") -> None:
        registrar_evento(action, detail, DB_PATH, self.username)

    def notify(self, text: str, color: str = C.accent) -> None:
        self.page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    def title(self, title: str, subtitle: str = "") -> ft.Row:
        return ft.Row(
            [
                ft.Column([ft.Text(title, size=26, weight=ft.FontWeight.BOLD, color=C.text), ft.Text(subtitle, size=12, color=C.muted) if subtitle else ft.Container()], spacing=4, expand=True),
            ],
            spacing=10,
        )

    def login_screen(self) -> None:
        self.page.controls.clear()
        self.page.bgcolor = "#EAEDEA"
        login_width = 390
        if not login_configurado(DB_PATH):
            content = ft.Column(
                [
                    ft.Text("SindEx", size=30, weight=ft.FontWeight.BOLD, color=C.text, text_align=ft.TextAlign.CENTER),
                    ft.Text("Primer uso: crea la contraseña del administrador.", size=13, color=C.muted, text_align=ft.TextAlign.CENTER),
                    ft.Container(self.admin_password, width=login_width),
                    ft.Container(self.admin_confirm, width=login_width),
                    ft.Row(
                        [primary("Crear administrador", self.create_admin, _icon("SHIELD")), secondary("Salir", self.exit_app, _icon("CLOSE"))],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            login_controls: list[ft.Control] = [
                ft.Text("SindEx", size=30, weight=ft.FontWeight.BOLD, color=C.text, text_align=ft.TextAlign.CENTER),
                ft.Text("Ingresa con tu usuario y contraseña", size=13, color=C.muted, text_align=ft.TextAlign.CENTER),
                ft.Container(self.login_user, width=login_width),
                ft.Container(self.login_password, width=login_width),
                ft.Row(
                    [
                        primary("Ingresar", self.login, _icon("LOGIN")),
                        secondary("Crear usuario básico", self.open_basic_login, _icon("PERSON_ADD")),
                        secondary("Salir", self.exit_app, _icon("CLOSE")),
                    ],
                    spacing=10,
                    wrap=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ]
            if self.show_create_login:
                login_controls.extend(
                    [
                        ft.Divider(color=C.line),
                        ft.Text("Crear usuario básico", size=15, weight=ft.FontWeight.BOLD, color=C.text, text_align=ft.TextAlign.CENTER),
                        ft.Container(
                            ft.Text(
                                "Ingresa nombre y apellido. El usuario se genera como inicial + apellido y la contraseña inicial será 1234.",
                                size=12,
                                color=C.muted,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            width=login_width,
                        ),
                        ft.Container(self.new_login_name, width=login_width),
                        ft.Row(
                            [
                                primary("Crear y autocompletar", self.create_basic_login, _icon("PERSON_ADD")),
                                secondary("Cancelar", self.cancel_basic_login, _icon("CLOSE")),
                            ],
                            spacing=10,
                            wrap=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ]
                )
            content = ft.Column(
                login_controls,
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        self.page.add(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Container(
                            content=card(content, padding=24),
                            width=520,
                        )
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                alignment=ft.Alignment(0, 0),
                padding=24,
            )
        )
        self.page.update()

    def exit_app(self, _e=None) -> None:
        registrar_evento("login_cancelado", "usuario salio desde login", DB_PATH)
        self.page.controls.clear()
        self.page.add(
            ft.Container(
                card(
                    ft.Column(
                        [
                            ft.Text("SindEx", size=30, weight=ft.FontWeight.BOLD, color=C.text),
                            ft.Text("Aplicación cerrada", size=18, weight=ft.FontWeight.BOLD, color=C.text),
                            ft.Text("Puedes cerrar esta pestaña del navegador.", size=13, color=C.muted),
                        ],
                        spacing=10,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=28,
                ),
                expand=True,
                alignment=ft.Alignment(0, 0),
                padding=24,
            )
        )
        self.page.update()

    def create_admin(self, _e=None) -> None:
        password = self.admin_password.value or ""
        confirm = self.admin_confirm.value or ""
        if len(password) < 6:
            self.notify("Usa una contraseña de al menos 6 caracteres.", C.red_text)
            return
        if password != confirm:
            self.notify("Las contraseñas no coinciden.", C.red_text)
            return
        try:
            crear_usuario("admin", password, "admin", DB_PATH)
            self.user = verificar_usuario("admin", password, DB_PATH)
            registrar_evento("seguridad", "usuario administrador inicial configurado", DB_PATH, "admin")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.view = "dashboard"
        self.refresh()

    def open_basic_login(self, _e=None) -> None:
        self.new_login_name.value = ""
        self.show_create_login = True
        self.login_screen()

    def cancel_basic_login(self, _e=None) -> None:
        self.new_login_name.value = ""
        self.show_create_login = False
        self.login_screen()

    def create_basic_login(self, _e=None) -> None:
        try:
            username = crear_usuario_basico(self.new_login_name.value or "", DB_PATH)
            if not usuario_existe(username, DB_PATH):
                raise RuntimeError("El usuario fue creado, pero no quedó activo en la base.")
            registrar_evento("usuario_auto_creado", f"usuario={username}; password_inicial=1234", DB_PATH, username)
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.show_create_login = False
        self.login_user.value = username
        self.login_password.value = "1234"
        self.login_screen()
        self.notify(f"Usuario creado: {username}. Contraseña inicial: 1234.")

    def login(self, _e=None) -> None:
        username = (self.login_user.value or "").strip().lower()
        password = self.login_password.value or ""
        if not username or not password:
            self.notify("Ingresa usuario y contraseña.", C.red_text)
            return
        if not usuario_existe(username, DB_PATH):
            self.notify("Usuario no existe. Puedes crear un usuario básico.", C.red_text)
            return
        user = verificar_usuario(username, password, DB_PATH)
        if not user:
            registrar_evento("login_fallido", "credenciales invalidas", DB_PATH, username)
            self.notify("Usuario o contraseña incorrectos.", C.red_text)
            return
        if user.get("rol") == "basico" and user.get("password_inicial"):
            uses = int(user.get("usos_password_inicial", 0))
            if uses >= 2:
                self.force_password_change(str(user["username"]))
                return
            user["usos_password_inicial"] = registrar_uso_password_inicial(str(user["username"]), DB_PATH)
            if int(user["usos_password_inicial"]) == 2:
                self.notify("Segundo ingreso con 1234. En el próximo ingreso deberá cambiarla.", C.amber_text)
        registrar_evento("login_ok", f"rol={user['rol']}", DB_PATH, str(user["username"]))
        self.user = user
        self.view = "dashboard"
        self.refresh()

    def force_password_change(self, username: str) -> None:
        new = field("Nueva contraseña", password=True)
        confirm = field("Confirmar contraseña", password=True)

        def save(_e=None) -> None:
            if new.value != confirm.value:
                self.notify("Las contraseñas no coinciden.", C.red_text)
                return
            try:
                cambiar_password_usuario(username, new.value or "", DB_PATH)
                self.user = verificar_usuario(username, new.value or "", DB_PATH)
                registrar_evento("cambio_password_obligatorio", "contraseña inicial reemplazada", DB_PATH, username)
            except Exception as exc:
                self.notify(str(exc), C.red_text)
                return
            self.close_dialog()
            self.view = "dashboard"
            self.refresh()

        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambio obligatorio"),
            content=ft.Column([ft.Text("La contraseña inicial 1234 ya fue usada dos veces."), new, confirm], tight=True, height=170),
            actions=[primary("Cambiar y entrar", save)],
        )
        self.page.dialog.open = True
        self.page.update()

    def close_dialog(self) -> None:
        if self.page.dialog:
            self.page.dialog.open = False
            self.page.update()

    def shell(self, content: ft.Control) -> None:
        items = [
            ("dashboard", "Dashboard", "DASHBOARD"),
            ("socios", "Socios", "GROUP"),
            ("buscar", "Buscar RUT", "SEARCH"),
            ("descuentos", "Descuentos", "PAYMENTS"),
            ("conciliar", "Conciliar", "COMPARE_ARROWS"),
            ("reportes", "Reportes", "BAR_CHART"),
            ("historial", "Historial", "CALENDAR_MONTH"),
            ("config", "Configuración", "SETTINGS"),
        ]
        if self.is_admin:
            items.append(("seguridad", "Seguridad", "SHIELD"))
        buttons = []
        for key, label, icon_name in items:
            active = key == self.view
            buttons.append(
                ft.Container(
                    ft.Row([ft.Icon(_icon(icon_name), size=16, color="#FFFFFF" if active else "#A9C5C8"), ft.Text(label, size=13, color="#FFFFFF" if active else "#A9C5C8", weight=ft.FontWeight.W_600 if active else None)], spacing=10),
                    bgcolor=C.active if active else C.sidebar,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=14, vertical=11),
                    ink=True,
                    on_click=lambda _e, view=key: self.go(view),
                )
            )
        sidebar = ft.Container(
            ft.Column(
                [
                    ft.Column(
                        [
                            ft.Text("SindEx", size=30, color="#FFFFFF", weight=ft.FontWeight.BOLD),
                            ft.Text("Sistema de Descuentos\nSindicato", size=10, color="#C6DADD"),
                        ],
                        spacing=2,
                    ),
                    ft.Column(buttons, spacing=5, expand=True),
                    ft.Column([ft.Text(f"Sesión: {self.username}", size=10, color="#C6DADD"), ft.Text("Desarrollado por\nOrveDevs 2026", size=10, color="#C6DADD"), sidebar_button("Cerrar sesión", self.logout, _icon("LOGOUT"))], spacing=10),
                ],
                spacing=28,
            ),
            width=230,
            bgcolor=C.sidebar,
            padding=ft.padding.only(left=18, top=22, right=18, bottom=18),
        )
        main = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Sistema de Descuentos Sindicato", size=13, weight=ft.FontWeight.BOLD, color=C.text, expand=True),
                            ft.Container(ft.Text(f"Apertura: {self.opened_at}", size=10, color=C.accent_dark), bgcolor="#EFF7F4", border_radius=10, padding=ft.padding.symmetric(horizontal=9, vertical=5)),
                            ft.Container(ft.Text("BD conectada", size=10, color=C.mint_text), bgcolor=C.mint, border_radius=10, padding=ft.padding.symmetric(horizontal=9, vertical=5)),
                        ],
                        spacing=10,
                    ),
                    ft.Container(content, expand=True),
                ],
                spacing=18,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.only(left=28, top=22, right=28, bottom=24),
        )
        self.page.controls.clear()
        self.page.add(ft.Row([sidebar, main], spacing=0, expand=True))
        self.page.update()

    def refresh(self) -> None:
        builders = {
            "dashboard": self.dashboard,
            "socios": self.socios,
            "buscar": self.buscar,
            "descuentos": self.descuentos,
            "conciliar": self.conciliar,
            "reportes": self.reportes,
            "historial": self.historial,
            "config": self.config,
            "seguridad": self.seguridad,
        }
        if self.view == "seguridad" and not self.is_admin:
            self.view = "dashboard"
        self.shell(builders[self.view]())

    def go(self, view: str) -> None:
        self.view = view
        self.refresh()

    def logout(self, _e=None) -> None:
        self.log("logout", "sesion cerrada")
        self.user = None
        self.login_screen()

    def dashboard(self) -> ft.Control:
        socios = obtener_resumen_socios(DB_PATH)
        months = _months_with_conciliation()
        month = months[0] if months else ""
        resumen = resumen_conciliacion(month, DB_PATH) if month else {"total_enviado_funs": 0, "total_descontado_cesjun": 0, "diferencia": 0, "estados": {}}
        detail = obtener_detalle_conciliacion(month, DB_PATH) if month else []
        pending = [row for row in detail if row["estado"] != "ok"]
        rows = [[chip(r["estado"]), r["rut"], r["nombre"], _money(r["diferencia"])] for r in pending[:80]]
        estado_controls = [
            ft.Row(
                [chip(k), ft.Text(str(v), size=18, weight=ft.FontWeight.BOLD)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            for k, v in resumen["estados"].items()
        ] or [ft.Text("Sin conciliaciones guardadas.", color=C.muted)]
        return ft.Column(
            [
                self.title("Dashboard inicial", "Resumen ejecutivo del padrón, conciliación y alertas."),
                ft.ResponsiveRow(
                    [
                        ft.Container(metric("Socios activos", str(socios["activos"]), f"de {socios['total']} registrados"), col={"xs": 12, "md": 4, "lg": 2}),
                        ft.Container(metric("Total FUNS enviado", _money(resumen["total_enviado_funs"]), month or "sin mes"), col={"xs": 12, "md": 4, "lg": 2}),
                        ft.Container(metric("Total CESJUN descontado", _money(resumen["total_descontado_cesjun"]), "según planilla"), col={"xs": 12, "md": 4, "lg": 2}),
                        ft.Container(metric("Diferencia detectada", _money(resumen["diferencia"]), "revisar", "warn" if int(resumen["diferencia"]) else "ok"), col={"xs": 12, "md": 4, "lg": 2}),
                        ft.Container(metric("Casos por revisar", str(len(pending)), "observables", "bad" if pending else "ok"), col={"xs": 12, "md": 4, "lg": 2}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                ft.Row(
                    [
                        card(ft.Column([ft.Text("Resumen por estado", weight=ft.FontWeight.BOLD, color=C.text), *estado_controls], spacing=12), expand=1),
                        card(ft.Column([ft.Row([ft.Text("Últimas alertas", weight=ft.FontWeight.BOLD, color=C.text), secondary("Ir a Conciliar", lambda _e: self.go("conciliar"))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), table(["Estado", "RUT", "Nombre", "Diferencia"], rows) if rows else ft.Text("Sin casos pendientes en el último mes conciliado.", color=C.muted)], spacing=12), expand=2),
                    ],
                    spacing=16,
                    expand=True,
                ),
            ],
            spacing=18,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def socios(self) -> ft.Control:
        resumen = obtener_resumen_socios(DB_PATH)
        rows = [[s["rut"], s["nombre"], s["local"], "Sí" if int(s["activo"]) else "No", s["mes_carga"]] for s in listar_socios(True, 300, DB_PATH)]
        return ft.Column(
            [
                self.title("Socios", "Carga y revisión del padrón de socios activos."),
                card(ft.Column([ft.Row([self.socios_month, self.socios_file, secondary("Seleccionar", self.pick_socios_file), primary("Cargar padrón", self.load_socios)], spacing=10, wrap=True), ft.Row([metric("Socios activos", str(resumen["activos"]), f"último mes {resumen['ultimo_mes'] or '-'}"), metric("Socios totales", str(resumen["total"]), "base local")], spacing=12)], spacing=14)),
                card(ft.Column([ft.Text("Socios activos recientes", weight=ft.FontWeight.BOLD, color=C.text), table(["RUT", "Nombre", "Local", "Activo", "Mes carga"], rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def buscar(self) -> ft.Control:
        rut_raw = (self.search_rut.value or "").strip()
        controls: list[ft.Control] = [self.title("Buscar RUT", "Consulta datos del socio y descuentos asociados."), card(ft.Row([self.search_rut, primary("Buscar RUT", self.search, _icon("SEARCH")), secondary("Limpiar", self.clear_search)], spacing=10, wrap=True))]
        if not rut_raw:
            rows = [[s["rut"], s["nombre"], s["local"], s["mes_carga"]] for s in listar_socios(True, 80, DB_PATH)]
            controls.append(card(ft.Column([ft.Text("Socios activos recientes", weight=ft.FontWeight.BOLD), table(["RUT", "Nombre", "Local", "Mes carga"], rows)], spacing=10), expand=True))
        else:
            try:
                rut = preparar_rut_para_busqueda(rut_raw)
                socio = buscar_socio_por_rut(rut, DB_PATH)
                desc = obtener_descuentos_ultimo_mes_rut(rut, DB_PATH)
                cesjun = obtener_cesjun_ultimo_mes_rut(rut, DB_PATH)
                hist = obtener_historial_descuentos_rut(rut, DB_PATH)
                controls.extend(
                    [
                        ft.ResponsiveRow(
                            [
                                ft.Container(metric("RUT", rut, "normalizado"), col={"xs": 12, "md": 6, "lg": 3}),
                                ft.Container(metric("Socio", socio["nombre"] if socio else "No encontrado", socio["local"] if socio else "sin padrón", "ok" if socio else "bad"), col={"xs": 12, "md": 6, "lg": 3}),
                                ft.Container(metric("FUNS último mes", _money(desc["total"]) if desc else "$0", desc["mes"] if desc else "sin descuentos", "warn" if not desc else "ok"), col={"xs": 12, "md": 6, "lg": 3}),
                                ft.Container(metric("CESJUN último mes", _money(cesjun["total"]) if cesjun else "$0", cesjun["mes"] if cesjun else "sin planilla", "warn" if not cesjun else "ok"), col={"xs": 12, "md": 6, "lg": 3}),
                            ],
                            spacing=12,
                            run_spacing=12,
                        ),
                        card(ft.Column([ft.Text("Historial de descuentos variables ingresados", weight=ft.FontWeight.BOLD), table(["Mes", "Tipo", "Monto", "Descripción"], [[h["mes"], h["tipo"], _money(h["monto"]), h["descripcion"]] for h in hist])], spacing=10), expand=True),
                    ]
                )
            except ValueError:
                controls.append(card(ft.Text("RUT inválido.", color=C.red_text)))
        return ft.Column(controls, spacing=16, expand=True, scroll=ft.ScrollMode.AUTO)

    def search(self, _e=None) -> None:
        try:
            rut = preparar_rut_para_busqueda(self.search_rut.value or "")
            self.search_rut.value = rut
            self.log("buscar_rut", f"rut={rut}")
        except ValueError as exc:
            self.notify(str(exc), C.red_text)
            return
        self.refresh()

    def clear_search(self, _e=None) -> None:
        self.search_rut.value = ""
        self.refresh()

    def descuentos(self) -> ft.Control:
        self.refresh_types()
        month = self.desc_month.value or _today_month()
        discounts = listar_descuentos_mes(month, DB_PATH)
        totals = obtener_totales_por_rut_mes(month, DB_PATH)
        total = sum(int(d["monto"]) for d in discounts)
        rows = [
            [
                ft.Checkbox(value=self.selected_discount_id == int(d["id"]), on_change=lambda _e, did=int(d["id"]): self.select_discount(did)),
                d["rut"], d["nombre"], d["tipo"], _money(d["monto"]), d["descripcion"],
            ]
            for d in discounts
        ]
        return ft.Column(
            [
                self.title("Descuentos", "Ingreso de descuentos variables y consolidado FUNS."),
                card(ft.Column([ft.Row([self.desc_month, self.desc_rut, self.desc_type, self.desc_amount, primary("Guardar descuento", self.add_discount, _icon("SAVE"))], spacing=10, wrap=True), ft.Row([self.desc_description, self.new_type, secondary("Agregar tipo", self.add_type), secondary("Eliminar seleccionado", self.delete_discount), primary("Exportar FUNS consolidado", self.export_discounts)], spacing=10, wrap=True)], spacing=12)),
                ft.ResponsiveRow([ft.Container(metric("Total mes", _money(total), f"{len(discounts)} descuentos"), col={"xs": 12, "md": 4}), ft.Container(metric("Socios con descuento", str(len(totals)), "consolidado por RUT"), col={"xs": 12, "md": 4})], spacing=12),
                card(ft.Column([ft.Text("Tabla de descuentos del mes", weight=ft.FontWeight.BOLD), table(["", "RUT", "Nombre", "Tipo", "Monto", "Descripción"], rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def refresh_types(self) -> None:
        types = listar_tipos_descuento(DB_PATH)
        self.desc_type.options = [ft.dropdown.Option(t) for t in types]
        if types and not self.desc_type.value:
            self.desc_type.value = types[0]

    def select_discount(self, discount_id: int) -> None:
        self.selected_discount_id = discount_id
        self.refresh()

    def add_discount(self, _e=None) -> None:
        try:
            month = _parse_month(self.desc_month.value or "")
            rut = preparar_rut_para_busqueda(self.desc_rut.value or "")
            amount = _parse_money(self.desc_amount.value or "")
            dtype = self.desc_type.value or ""
            if not dtype:
                raise ValueError("Selecciona un tipo de descuento.")
            guardar_descuento_mensual(rut, month, dtype, amount, self.desc_description.value or "", DB_PATH)
            self.log("agregar_descuento", f"mes={month}; rut={rut}; tipo={dtype}; monto={amount}")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.desc_rut.value = ""
        self.desc_amount.value = ""
        self.desc_description.value = ""
        self.notify("Descuento guardado.")
        self.refresh()

    def add_type(self, _e=None) -> None:
        name = (self.new_type.value or "").strip()
        if not name:
            self.notify("Ingresa el nombre del tipo.", C.red_text)
            return
        if agregar_tipo_descuento(name, DB_PATH):
            self.log("agregar_tipo_descuento", f"tipo={name}")
            self.desc_type.value = name
            self.new_type.value = ""
            self.notify("Tipo agregado.")
        else:
            self.notify("Ese tipo ya existe.", C.amber_text)
        self.refresh()

    def delete_discount(self, _e=None) -> None:
        if not self.selected_discount_id:
            self.notify("Selecciona un descuento de la tabla.", C.amber_text)
            return
        eliminar_descuento_mensual(self.selected_discount_id, DB_PATH)
        self.log("eliminar_descuento", f"id={self.selected_discount_id}")
        self.selected_discount_id = None
        self.notify("Descuento eliminado.")
        self.refresh()

    def conciliar(self) -> ft.Control:
        month = self.conc_month.value or _today_month()
        resumen = resumen_conciliacion(month, DB_PATH)
        detail = obtener_detalle_conciliacion(month, DB_PATH)
        rows = [[chip(d["estado"]), d["rut"], d["nombre"], _money(d["total_calculado"]), _money(d["total_descontado"]), _money(d["diferencia"])] for d in detail[:200]]
        return ft.Column(
            [
                self.title("Conciliación", "Cruce de planilla mensual CESJUN/SIJUAN contra FUNS."),
                card(ft.Column([ft.Row([self.conc_month, self.conc_monthly_file, secondary("Planilla mensual", self.pick_monthly_file)], spacing=10, wrap=True), ft.Row([self.conc_funs_file, secondary("Archivo FUNS", self.pick_funs_file), primary("Conciliar mes", self.run_conciliation), secondary("Exportar este mes", self.export_current_report)], spacing=10, wrap=True)], spacing=12)),
                ft.ResponsiveRow([ft.Container(metric("Total enviado", _money(resumen["total_enviado_funs"]), "FUNS"), col={"xs": 12, "md": 3}), ft.Container(metric("Total descontado", _money(resumen["total_descontado_cesjun"]), "CESJUN"), col={"xs": 12, "md": 3}), ft.Container(metric("Diferencia total", _money(resumen["diferencia"]), "resultado", "warn" if int(resumen["diferencia"]) else "ok"), col={"xs": 12, "md": 3}), ft.Container(metric("Casos", str(len(detail)), "conciliados"), col={"xs": 12, "md": 3})], spacing=12),
                card(ft.Column([ft.Text("Detalle de conciliación", weight=ft.FontWeight.BOLD), table(["Estado", "RUT", "Nombre", "FUNS", "CESJUN", "Diferencia"], rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def reportes(self) -> ft.Control:
        months = _months_with_conciliation()
        if not self.report_month.value and months:
            self.report_month.value = months[0]
        month = self.report_month.value or ""
        resumen = resumen_conciliacion(month, DB_PATH) if month else {"total_enviado_funs": 0, "total_descontado_cesjun": 0, "diferencia": 0}
        detail = obtener_detalle_conciliacion(month, DB_PATH) if month else []
        rows = [[chip(d["estado"]), d["rut"], d["nombre"], _money(d["diferencia"])] for d in detail[:200]]
        return ft.Column(
            [
                self.title("Reportes", "Resumen administrativo de meses conciliados."),
                card(ft.Row([self.report_month, secondary("Usar último mes", self.use_latest_month), primary("Ver resumen", lambda _e: self.refresh()), primary("Exportar Excel", self.export_report_tab)], spacing=10, wrap=True)),
                ft.ResponsiveRow([ft.Container(metric("Total FUNS", _money(resumen["total_enviado_funs"]), month or "sin mes"), col={"xs": 12, "md": 4}), ft.Container(metric("Total CESJUN", _money(resumen["total_descontado_cesjun"]), "descontado"), col={"xs": 12, "md": 4}), ft.Container(metric("Diferencia", _money(resumen["diferencia"]), "control", "warn" if int(resumen["diferencia"]) else "ok"), col={"xs": 12, "md": 4})], spacing=12),
                card(ft.Column([ft.Text("Detalle del mes", weight=ft.FontWeight.BOLD), table(["Estado", "RUT", "Nombre", "Diferencia"], rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def historial(self) -> ft.Control:
        try:
            year = int(self.history_year.value or _today_year())
        except ValueError:
            year = date.today().year
        rut_filter = None
        if self.history_rut.value:
            try:
                rut_filter = preparar_rut_para_busqueda(self.history_rut.value)
                self.history_rut.value = rut_filter
            except ValueError:
                rut_filter = None
        months, rows_data = obtener_datos_historial(DB_PATH, rut_filter, year)
        headers = ["RUT", "Nombre"] + [MONTH_NAMES[int(m[-2:]) - 1] for m in months]
        rows = []
        for row in rows_data[:250]:
            values = [row["rut"], row["nombre"]]
            values.extend(_money(row.get(month)) if row.get(month) is not None else "sin descuento" for month in months)
            rows.append(values)
        return ft.Column(
            [
                self.title("Historial anual", "Matriz anual desde CESJUN: columnas por mes y filas por socio."),
                card(ft.Row([self.history_year, self.history_rut, primary("Filtrar", lambda _e: self.refresh()), secondary("Limpiar", self.clear_history), primary("Exportar historial Excel", self.export_history)], spacing=10, wrap=True)),
                card(ft.Column([ft.Row([ft.Text(f"Año {year} · Personas {len(rows_data)} · 12 meses", weight=ft.FontWeight.BOLD, color=C.text), ft.Text("Los valores vienen de la hoja CESJUN cargada mes a mes.", size=11, color=C.muted)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), table(headers, rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def config(self) -> ft.Control:
        return ft.Column(
            [
                self.title("Configuración", "Cuenta y contraseña de acceso."),
                ft.ResponsiveRow([ft.Container(metric("Usuario", self.username, str((self.user or {}).get("rol", ""))), col={"xs": 12, "md": 4}), ft.Container(metric("Usos 1234", str((self.user or {}).get("usos_password_inicial", 0)), "contraseña inicial"), col={"xs": 12, "md": 4})], spacing=12),
                card(ft.Column([ft.Text("Cambiar contraseña", weight=ft.FontWeight.BOLD, color=C.text), ft.Row([self.current_password, self.new_password, self.confirm_password, primary("Actualizar", self.change_password)], spacing=10, wrap=True)], spacing=12)),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def seguridad(self) -> ft.Control:
        users = listar_usuarios(DB_PATH)
        events = listar_eventos_recientes(80, DB_PATH)
        user_rows = [[ft.Checkbox(value=self.selected_username == u["username"], on_change=lambda _e, username=u["username"]: self.select_user(username)), u["username"], u["rol"], "Sí" if int(u["activo"]) else "No", u["usos_password_inicial"], u["creado_en"]] for u in users]
        event_rows = [[e["fecha_hora"], e["usuario"], e["accion"], e["detalle"]] for e in events]
        backup_dir = DB_PATH.parent / "backups"
        backups = sorted(backup_dir.glob("*.db"), reverse=True) if backup_dir.exists() else []
        return ft.Column(
            [
                self.title("Seguridad", "Usuarios, backups y registro de actividad."),
                ft.ResponsiveRow([ft.Container(metric("Usuarios activos", str(sum(1 for u in users if int(u["activo"]) == 1)), "control local"), col={"xs": 12, "md": 4}), ft.Container(metric("Backups", str(len(backups)), backups[0].name if backups else "sin respaldos"), col={"xs": 12, "md": 4})], spacing=12),
                card(ft.Column([ft.Text("Crear usuario básico", weight=ft.FontWeight.BOLD), ft.Row([self.security_name, primary("Crear usuario", self.create_user_security), secondary("Desactivar seleccionado", self.deactivate_user), primary("Crear backup ahora", self.create_backup)], spacing=10, wrap=True)], spacing=12)),
                card(ft.Column([ft.Text("Usuarios", weight=ft.FontWeight.BOLD), table(["", "Usuario", "Rol", "Activo", "Usos 1234", "Creado"], user_rows)], spacing=10)),
                card(ft.Column([ft.Text("Registro de actividad", weight=ft.FontWeight.BOLD), table(["Fecha", "Usuario", "Acción", "Detalle"], event_rows)], spacing=10), expand=True),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def load_socios(self, _e=None) -> None:
        try:
            month = _parse_month(self.socios_month.value or "")
            path = Path(self.socios_file.value or "")
            if not path.exists():
                raise ValueError("Selecciona un archivo válido.")
            crear_backup_automatico(DB_PATH, "antes_padron", self.username)
            data = importar_archivo_mensual(path)
            result = guardar_socios_desde_sijuan(data["socios"], month, DB_PATH)
            cesjun = 0
            if data["cesjun"]:
                cargar_cesjun_desde_registros(data["cesjun"], month, DB_PATH)
                cesjun = len(data["cesjun"])
            self.log("carga_padron", f"mes={month}; socios={len(data['socios'])}; cesjun={cesjun}")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.notify(f"Padrón cargado. Activos: {result['socios_activos']}.")
        self.refresh()

    def run_conciliation(self, _e=None) -> None:
        try:
            month = _parse_month(self.conc_month.value or "")
            monthly = Path(self.conc_monthly_file.value or "")
            funs = Path(self.conc_funs_file.value or "")
            if not monthly.exists() or not funs.exists():
                raise ValueError("Selecciona la planilla mensual y el archivo FUNS.")
            crear_backup_automatico(DB_PATH, "antes_conciliar", self.username)
            data = importar_archivo_mensual(monthly)
            if data["socios"]:
                guardar_socios_desde_sijuan(data["socios"], month, DB_PATH)
            cargar_cesjun_desde_registros(data["cesjun"], month, DB_PATH)
            cargar_funs_enviado_desde_excel(funs, month, DB_PATH)
            conciliar_mes(month, DB_PATH)
            detail = obtener_detalle_conciliacion(month, DB_PATH)
            self.report_month.value = month
            self.log("conciliacion", f"mes={month}; casos={len(detail)}")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        missing = obtener_casos_por_estado(month, "no_descontado", DB_PATH)
        self.notify(f"Conciliación lista. Casos no descontados: {len(missing)}.")
        self.refresh()

    def use_latest_month(self, _e=None) -> None:
        months = _months_with_conciliation()
        if not months:
            self.notify("Todavía no existen meses conciliados.", C.amber_text)
            return
        self.report_month.value = months[0]
        self.refresh()

    def clear_history(self, _e=None) -> None:
        self.history_rut.value = ""
        self.history_year.value = _today_year()
        self.refresh()

    def change_password(self, _e=None) -> None:
        if self.new_password.value != self.confirm_password.value:
            self.notify("Las contraseñas no coinciden.", C.red_text)
            return
        if not verificar_usuario(self.username, self.current_password.value or "", DB_PATH):
            self.notify("La contraseña actual no es correcta.", C.red_text)
            return
        try:
            cambiar_password_usuario(self.username, self.new_password.value or "", DB_PATH)
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.user = verificar_usuario(self.username, self.new_password.value or "", DB_PATH)
        self.current_password.value = ""
        self.new_password.value = ""
        self.confirm_password.value = ""
        self.log("cambio_password", "contraseña actualizada")
        self.notify("Contraseña actualizada.")
        self.refresh()

    def create_user_security(self, _e=None) -> None:
        try:
            username = crear_usuario_basico(self.security_name.value or "", DB_PATH)
            self.log("usuario_guardado", f"usuario={username}; rol=basico; password_inicial=1234")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.security_name.value = ""
        self.notify(f"Usuario creado: {username}. Contraseña inicial: 1234.")
        self.refresh()

    def select_user(self, username: str) -> None:
        self.selected_username = username
        self.refresh()

    def deactivate_user(self, _e=None) -> None:
        if not self.selected_username:
            self.notify("Selecciona un usuario.", C.amber_text)
            return
        try:
            desactivar_usuario(self.selected_username, DB_PATH)
            self.log("usuario_desactivado", f"usuario={self.selected_username}")
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.selected_username = ""
        self.notify("Usuario desactivado.")
        self.refresh()

    def create_backup(self, _e=None) -> None:
        try:
            backup = crear_backup_automatico(DB_PATH, "manual", self.username)
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.notify(f"Backup creado: {backup.name if backup else 'sin base de datos'}")
        self.refresh()

    async def export_discounts(self, _e=None) -> None:
        self.export_data = {"month": self.desc_month.value or _today_month()}
        self.save_action = "discounts"
        path = await self.save_picker.save_file(file_name=f"descuentos_funs_{self.export_data['month']}.xlsx", allowed_extensions=["xlsx"])
        if path:
            self._save_to_path(path)

    async def export_current_report(self, _e=None) -> None:
        self.export_data = {"month": self.conc_month.value or _today_month()}
        self.save_action = "report"
        path = await self.save_picker.save_file(file_name=f"reporte_conciliacion_{self.export_data['month']}.xlsx", allowed_extensions=["xlsx"])
        if path:
            self._save_to_path(path)

    async def export_report_tab(self, _e=None) -> None:
        self.export_data = {"month": self.report_month.value or _today_month()}
        self.save_action = "report"
        path = await self.save_picker.save_file(file_name=f"reporte_conciliacion_{self.export_data['month']}.xlsx", allowed_extensions=["xlsx"])
        if path:
            self._save_to_path(path)

    async def export_history(self, _e=None) -> None:
        self.export_data = {"year": self.history_year.value or _today_year(), "rut": self.history_rut.value or None}
        self.save_action = "history"
        path = await self.save_picker.save_file(file_name=f"historial_descuentos_{self.export_data['year']}.xlsx", allowed_extensions=["xlsx"])
        if path:
            self._save_to_path(path)

    def _save_to_path(self, path: str) -> None:
        try:
            if self.save_action == "discounts":
                month = _parse_month(str(self.export_data["month"]))
                output = exportar_descuentos_para_funs(month, path, DB_PATH)
                self.log("exportar_funs", f"mes={month}; archivo={Path(output).name}")
            elif self.save_action == "report":
                month = _parse_month(str(self.export_data["month"]))
                output = exportar_reporte_conciliacion(month, path, DB_PATH)
                self.log("exportar_reporte", f"mes={month}; archivo={Path(output).name}")
            elif self.save_action == "history":
                rut = self.export_data.get("rut")
                rut_filter = preparar_rut_para_busqueda(str(rut)) if rut else None
                output = exportar_historial_excel(path, DB_PATH, rut_filter, self.export_data.get("year"))
                self.log("exportar_historial", f"anio={self.export_data.get('year')}; archivo={Path(output).name}")
            else:
                return
        except Exception as exc:
            self.notify(str(exc), C.red_text)
            return
        self.notify(f"Archivo generado: {Path(output).name}")

    async def pick_file(self, target: str) -> None:
        self.file_target = target
        files = await self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["xlsx", "xlsm"])
        if not files:
            return
        path = files[0].path
        if self.file_target == "socios":
            self.socios_file.value = path
        elif self.file_target == "monthly":
            self.conc_monthly_file.value = path
        elif self.file_target == "funs":
            self.conc_funs_file.value = path
        self.page.update()

    async def pick_socios_file(self, _e=None) -> None:
        await self.pick_file("socios")

    async def pick_monthly_file(self, _e=None) -> None:
        await self.pick_file("monthly")

    async def pick_funs_file(self, _e=None) -> None:
        await self.pick_file("funs")


def run() -> None:
    ft.run(lambda page: SindExFlet(page), view=ft.AppView.WEB_BROWSER)
