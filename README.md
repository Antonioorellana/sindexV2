# SindEx V2

Sistema local para gestión de descuentos sindicales, conciliación mensual y reportes Excel.

Esta versión usa Flet para la interfaz gráfica y mantiene la lógica local en Python con SQLite.

## Funciones principales

- Login con usuario administrador y usuarios básicos.
- Registro de auditoría de acciones.
- Carga de padrón mensual y planilla CESJUN.
- Cruce contra planilla FUNS.
- Búsqueda por RUT.
- Historial anual de descuentos.
- Exportación Excel de reportes y consolidado FUNS.

## Instalación local

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Datos sensibles

Este repositorio no debe incluir bases de datos reales, planillas Excel reales ni backups.

Los siguientes archivos quedan ignorados por Git:

- `data/*.db`
- `data/backups/`
- `archivos/*.xlsx`
- `reportes/*.xlsx`

## Estado

Versión 2 en desarrollo, migrada a Flet.

