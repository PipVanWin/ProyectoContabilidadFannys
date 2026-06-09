"""
Servicio que ejecuta el cierre contable mensual completo en 4 pasos.

Este es el proceso más importante del ciclo contable. Al ejecutarse,
genera automáticamente las partidas de cierre y deja el período en
estado 'CERRADO', impidiendo nuevas transacciones en él.

Pasos del cierre (en orden obligatorio):

  Paso 1 — Regularización del IVA
            Compara IVA Débito Fiscal (2.1.2) vs IVA Crédito Fiscal (1.1.5)
            y genera la partida que salda ambas cuentas. Si el débito
            supera al crédito, la diferencia queda en IVA por Pagar (2.1.3).

  Paso 2 — Cierre de ingresos
            Salda la cuenta Ventas (4.1.1) contra Utilidad del Ejercicio (3.1.2).

  Paso 3 — Cierre de gastos
            Salda todas las cuentas de gasto (nivel 3) contra
            Utilidad del Ejercicio (3.1.2).

  Paso 4 — Cierre a capital
            Traslada la utilidad o pérdida neta a Capital Inicial (3.1.1).
            Si hay utilidad: aumenta el capital.
            Si hay pérdida: reduce el capital y registra en Pérdida (3.1.3).

Cuentas del plan contable utilizadas:
  1.1.5 — IVA Crédito Fiscal
  2.1.2 — IVA Débito Fiscal
  2.1.3 — IVA por Pagar
  3.1.1 — Capital Inicial
  3.1.2 — Utilidad del Ejercicio
  3.1.3 — Pérdida del Ejercicio
  4.1.1 — Ventas
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from models.models import (
    PeriodoContable, Transaccion, PartidaDiaria,
    DetallePartida, CuentaContable,
)
from datetime import date


def _linea(db, partida, codigo, debe=0, haber=0):
    """
    Agrega una línea de débito o crédito a una partida de cierre.

    Args:
        db (Session): Sesión de base de datos.
        partida (PartidaDiaria): Partida a la que pertenece la línea.
        codigo (str): Código de la cuenta contable a afectar.
        debe (float): Monto al debe (default: 0).
        haber (float): Monto al haber (default: 0).

    Raises:
        ValueError: Si el código de cuenta no existe en el catálogo.
    """
    cuenta = db.query(CuentaContable).filter_by(codigo=codigo).first()
    if not cuenta:
        raise ValueError(f"Cuenta {codigo} no encontrada")
    linea = DetallePartida(
        idpartida = partida.idpartida,
        idcuenta  = cuenta.id,
        debe      = debe,
        haber     = haber,
    )
    db.add(linea)


def _siguiente_numero_partida(db, idperiodo):
    """
    Calcula el número correlativo de la siguiente partida del período.

    Args:
        db (Session): Sesión de base de datos.
        idperiodo (int): ID del período contable.

    Returns:
        int: Número de la siguiente partida (último + 1).
    """
    ultimo = (
        db.query(func.max(PartidaDiaria.numero_partida))
        .join(Transaccion)
        .filter(Transaccion.idperiodo == idperiodo)
        .scalar()
    )
    return (ultimo or 0) + 1


def _crear_partida_cierre(db, idperiodo, concepto, tipo):
    """
    Crea una transacción y su partida de tipo CIERRE en el Libro Diario.

    Las partidas de cierre se distinguen de las normales por su tipo
    ('CIERRE' o 'REGULARIZACION') y se excluyen de los reportes
    operativos (Libro Mayor, Estado de Resultados).

    Args:
        db (Session): Sesión de base de datos.
        idperiodo (int): ID del período contable a cerrar.
        concepto (str): Descripción del asiento de cierre.
        tipo (str): Tipo de partida ('CIERRE' o 'REGULARIZACION').

    Returns:
        PartidaDiaria: Partida creada con su ID asignado.
    """
    tx = Transaccion(
        idperiodo   = idperiodo,
        fecha       = date.today(),
        tipo        = "CIERRE",
        descripcion = concepto,
        monto_base  = 0,
        iva         = 0,
    )
    db.add(tx)
    db.flush()

    num = _siguiente_numero_partida(db, idperiodo)
    partida = PartidaDiaria(
        idtransaccion  = tx.idtransaccion,
        numero_partida = num,
        fecha          = date.today(),
        concepto       = concepto,
        tipo_partida   = tipo,
    )
    db.add(partida)
    db.flush()
    return partida


def _saldo_cuenta(db, codigo, idperiodo):
    """
    Calcula el saldo neto de una cuenta contable en el período.

    El saldo se calcula según la naturaleza de la cuenta:
      - Cuentas DEUDORAS (Activo, Gasto): saldo = debe - haber
      - Cuentas ACREEDORAS (Pasivo, Capital, Ingreso): saldo = haber - debe

    Args:
        db (Session): Sesión de base de datos.
        codigo (str): Código de la cuenta contable.
        idperiodo (int): ID del período contable a consultar.

    Returns:
        float: Saldo neto de la cuenta. Retorna 0 si la cuenta no existe
        o no tiene movimientos en el período.
    """
    cuenta = db.query(CuentaContable).filter_by(codigo=codigo).first()
    if not cuenta:
        return 0
    resultado = (
        db.query(
            func.sum(DetallePartida.debe).label("debe"),
            func.sum(DetallePartida.haber).label("haber"),
        )
        .join(PartidaDiaria)
        .join(Transaccion)
        .filter(Transaccion.idperiodo == idperiodo)
        .filter(DetallePartida.idcuenta == cuenta.id)
        .first()
    )
    debe  = float(resultado.debe  or 0)
    haber = float(resultado.haber or 0)
    return debe - haber if cuenta.naturaleza == "DEUDORA" else haber - debe


def ejecutar_cierre_mensual(periodo: PeriodoContable, db: Session):
    """
    Ejecuta el cierre contable mensual completo en 4 pasos.

    Este proceso es irreversible: al finalizar, el período queda
    en estado 'CERRADO' y no puede recibir nuevas transacciones.
    Genera 4 partidas automáticas en el Libro Diario.

    Args:
        periodo (PeriodoContable): Objeto del período a cerrar.
            Debe estar en estado 'ABIERTO'.
        db (Session): Sesión de base de datos.

    Returns:
        dict: Resultado del cierre con:
            - mensaje (str): Confirmación del cierre con mes/año.
            - resumen (list): Lista de los 4 pasos ejecutados con
              concepto y monto de cada uno.
            - utilidad_neta (float): Resultado final del período
              (positivo = utilidad, negativo = pérdida).
    """
    idperiodo = periodo.idperiodo
    resumen   = []

    # ──Regularización del IVA 
    iva_debito  = _saldo_cuenta(db, "2.1.2", idperiodo)   # IVA Débito Fiscal
    iva_credito = _saldo_cuenta(db, "1.1.5", idperiodo)   # IVA Crédito Fiscal
    iva_neto    = round(iva_debito - iva_credito, 2)

    partida_iva = _crear_partida_cierre(
        db, idperiodo, "Regularización del IVA del período", "REGULARIZACION"
    )
    _linea(db, partida_iva, "2.1.2", debe=iva_debito)     # Cierra IVA Débito Fiscal
    _linea(db, partida_iva, "1.1.5", haber=iva_credito)   # Cierra IVA Crédito Fiscal
    if iva_neto > 0:
        _linea(db, partida_iva, "2.1.3", haber=iva_neto)  # IVA neto → por pagar a la SAT
    resumen.append({"paso": 1, "concepto": "Regularización IVA", "monto": iva_neto})

    # ──Cierre de ingresos 
    ventas = _saldo_cuenta(db, "4.1.1", idperiodo)
    partida_ing = _crear_partida_cierre(
        db, idperiodo, "Cierre de ingresos del período", "CIERRE"
    )
    _linea(db, partida_ing, "4.1.1", debe=ventas)         # Salda cuenta Ventas
    _linea(db, partida_ing, "3.1.2", haber=ventas)        # Acumula en Utilidad del Ejercicio
    resumen.append({"paso": 2, "concepto": "Cierre de ingresos", "monto": ventas})

    # ──Cierre de gastos 

    cuentas_gasto = db.query(CuentaContable).filter(
        CuentaContable.tipo  == "Gasto",
        CuentaContable.nivel == 3,
    ).all()

    total_gastos = 0
    partida_gas = _crear_partida_cierre(
        db, idperiodo, "Cierre de gastos del período", "CIERRE"
    )
    for cuenta in cuentas_gasto:
        saldo = _saldo_cuenta(db, cuenta.codigo, idperiodo)
        if saldo > 0:
            _linea(db, partida_gas, cuenta.codigo, haber=saldo)  
            total_gastos += saldo

    _linea(db, partida_gas, "3.1.2", debe=total_gastos)  
    resumen.append({"paso": 3, "concepto": "Cierre de gastos", "monto": total_gastos})

    # ──Cierre a capital 
    utilidad = round(ventas - total_gastos, 2)
    partida_cap = _crear_partida_cierre(
        db, idperiodo, "Traslado de resultado a capital", "CIERRE"
    )
    if utilidad >= 0:
        # Utilidad: aumenta el capital de la empresa
        _linea(db, partida_cap, "3.1.2", debe=utilidad)   
        _linea(db, partida_cap, "3.1.1", haber=utilidad) 
    else:
        # Pérdida: reduce el capital de la empresa
        perdida = abs(utilidad)
        _linea(db, partida_cap, "3.1.1", debe=perdida)    
        _linea(db, partida_cap, "3.1.3", haber=perdida)   
    resumen.append({"paso": 4, "concepto": "Cierre a capital", "monto": utilidad})

    # Cerrar Periodo
    periodo.estado = "CERRADO"
    db.commit()

    return {
        "mensaje":       f"Período {periodo.mes}/{periodo.anio} cerrado exitosamente",
        "resumen":       resumen,
        "utilidad_neta": utilidad,
    }
