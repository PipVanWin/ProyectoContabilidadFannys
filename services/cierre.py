# services/cierre.py
# Ejecuta el cierre contable mensual completo en 4 pasos:
#
#   Paso 1 — Regularización del IVA
#             Compara IVA Débito (ventas) vs IVA Crédito (compras/gastos)
#             y genera la partida que salda ambas cuentas.
#
#   Paso 2 — Cierre de ingresos
#             Salda la cuenta Ventas contra Pérdidas y Ganancias.
#
#   Paso 3 — Cierre de gastos
#             Salda todas las cuentas de gasto contra Pérdidas y Ganancias.
#
#   Paso 4 — Cierre a capital
#             Traslada el resultado (utilidad o pérdida) a Capital.

from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models.models import (
    PeriodoContable, Transaccion, PartidaDiaria,
    DetallePartida, CuentaContable, 
)
def _linea(db, partida, codigo, debe=0, haber=0):
    from models.models import CuentaContable, DetallePartida
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
    from sqlalchemy import func
    from models.models import PartidaDiaria, Transaccion
    ultimo = (
        db.query(func.max(PartidaDiaria.numero_partida))
        .join(Transaccion)
        .filter(Transaccion.idperiodo == idperiodo)
        .scalar()
    )
    return (ultimo or 0) + 1
from datetime import date


def _crear_partida_cierre(db, idperiodo, concepto, tipo):
    """Crea una transacción y partida de tipo CIERRE."""
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
    """Calcula el saldo neto de una cuenta en el período."""
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
    """Ejecuta los 4 pasos del cierre contable."""
    idperiodo = periodo.idperiodo
    resumen   = []

    # ── Paso 1: Regularización del IVA ──────────────────────────
    iva_debito  = _saldo_cuenta(db, "2.1.2", idperiodo)   # IVA Débito Fiscal
    iva_credito = _saldo_cuenta(db, "1.1.5", idperiodo)   # IVA Crédito Fiscal
    iva_neto    = round(iva_debito - iva_credito, 2)

    partida_iva = _crear_partida_cierre(
        db, idperiodo, "Regularización del IVA del período", "REGULARIZACION"
    )
    _linea(db, partida_iva, "2.1.2", debe=iva_debito)     # Cierra IVA Débito
    _linea(db, partida_iva, "1.1.5", haber=iva_credito)   # Cierra IVA Crédito
    if iva_neto > 0:
        _linea(db, partida_iva, "2.1.3", haber=iva_neto)  # IVA por Pagar
    resumen.append({"paso": 1, "concepto": "Regularización IVA", "monto": iva_neto})

    # ── Paso 2: Cierre de ingresos ───────────────────────────────
    ventas = _saldo_cuenta(db, "4.1.1", idperiodo)
    partida_ing = _crear_partida_cierre(
        db, idperiodo, "Cierre de ingresos del período", "CIERRE"
    )
    _linea(db, partida_ing, "4.1.1",  debe=ventas)        # Salda Ventas
    _linea(db, partida_ing, "3.1.2",  haber=ventas)       # A Utilidad del Ejercicio
    resumen.append({"paso": 2, "concepto": "Cierre de ingresos", "monto": ventas})

    # ── Paso 3: Cierre de gastos ─────────────────────────────────
    cuentas_gasto = db.query(CuentaContable).filter(
        CuentaContable.tipo == "Gasto",
        CuentaContable.nivel == 3,
    ).all()

    total_gastos = 0
    partida_gas = _crear_partida_cierre(
        db, idperiodo, "Cierre de gastos del período", "CIERRE"
    )
    for cuenta in cuentas_gasto:
        saldo = _saldo_cuenta(db, cuenta.codigo, idperiodo)
        if saldo > 0:
            _linea(db, partida_gas, cuenta.codigo, haber=saldo)  # Salda cada gasto
            total_gastos += saldo

    _linea(db, partida_gas, "3.1.2", debe=total_gastos)   # Reduce Utilidad del Ejercicio
    resumen.append({"paso": 3, "concepto": "Cierre de gastos", "monto": total_gastos})

    # ── Paso 4: Cierre a capital 
    utilidad = round(ventas - total_gastos, 2)
    partida_cap = _crear_partida_cierre(
        db, idperiodo, "Traslado de resultado a capital", "CIERRE"
    )
    if utilidad >= 0:
        _linea(db, partida_cap, "3.1.2", debe=utilidad)   # Salda Utilidad
        _linea(db, partida_cap, "3.1.1", haber=utilidad)  # A Capital Inicial
    else:
        perdida = abs(utilidad)
        _linea(db, partida_cap, "3.1.1", debe=perdida)    # Reduce Capital
        _linea(db, partida_cap, "3.1.3", haber=perdida)   # Pérdida del Ejercicio
    resumen.append({"paso": 4, "concepto": "Cierre a capital", "monto": utilidad})

    # ── Marcar período como cerrado 
    periodo.estado = "CERRADO"
    db.commit()

    return {
        "mensaje": f"Período {periodo.mes}/{periodo.anio} cerrado exitosamente",
        "resumen": resumen,
        "utilidad_neta": utilidad,
    }
