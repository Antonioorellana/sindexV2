from __future__ import annotations


def _limpiar_rut(rut: str) -> str:
    return str(rut or "").strip().upper().replace(".", "").replace("-", "")


def normalizar_rut(rut: str) -> str:
    limpio = _limpiar_rut(rut)
    if len(limpio) < 2:
        raise ValueError("RUT incompleto")
    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit() or not (dv.isdigit() or dv == "K"):
        raise ValueError("RUT contiene caracteres invalidos")
    return f"{int(cuerpo)}-{dv}"


def _calcular_dv(cuerpo: str) -> str:
    serie = [2, 3, 4, 5, 6, 7]
    total = 0
    for indice, digito in enumerate(reversed(cuerpo)):
        total += int(digito) * serie[indice % len(serie)]
    resto = 11 - (total % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(rut: str) -> bool:
    try:
        normalizado = normalizar_rut(rut)
    except ValueError:
        return False
    cuerpo, dv = normalizado.split("-")
    return _calcular_dv(cuerpo) == dv


def preparar_rut_para_busqueda(rut: str) -> str:
    if not validar_rut(rut):
        raise ValueError("RUT invalido")
    return normalizar_rut(rut)

