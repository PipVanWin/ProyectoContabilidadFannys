# services/contabilidad.py
# Lógica central del sistema: convierte una transacción
# en una partida de libro diario con partida doble automática.
#
# Reglas contables aplicadas:
#   VENTA  → Debe: Caja/Banco + IVA Débito Fiscal | Haber: Ventas
#   COMPRA → Debe: Inventario + IVA Crédito Fiscal | Haber: Caja/Banco + Cuentas por Pagar
#   GASTO  → Debe: Cuenta de Gasto + IVA Crédito   | Haber: Caja/Banco

from sqlalchemy.orm import Session
from models.models import (
    Transaccion, PartidaDiaria, DetallePartida, CuentaContable, PeriodoContable
)
from config import TASA_IVA
from datetime import date


def _obtener_cuenta(db: Session, codigo: str) -> CuentaContable:
    """Busca una cuenta por su código. Lanza error si no existe."""
    cuenta = db.query(CuentaContable).filter_by(codigo=codigo).first()
    if not cuenta:
        raise ValueError(f"Cuenta {codigo} no encontrada en el catálogo")
    return cuenta


def _siguiente_numero_partida(db: Session, idperiodo: int) -> int:
    """Calcula el siguiente número de partida del período."""
    from sqlalchemy import func
    from models.models import PartidaDiaria, Transaccion
    ultimo = (
        db.query(func.max(PartidaDiaria.numero_partida))
        .join(Transaccion)
        .filter(Transaccion.idperiodo == idperiodo)
        .scalar()
    )
    return (ultimo or 0) + 1


def _crear_partida(db, transaccion, concepto, tipo="NORMAL"):
    """Crea el encabezado de la partida en el libro diario."""
    num = _siguiente_numero_partida(db, transaccion.idperiodo)
    partida = PartidaDiaria(
        idtransaccion  = transaccion.idtransaccion,
        numero_partida = num,
        fecha          = transaccion.fecha,
        concepto       = concepto,
        tipo_partida   = tipo,
    )
    db.add(partida)
    db.flush()  # flush para obtener el idpartida sin hacer commit aún
    return partida


def _linea(db, partida, codigo_cuenta, debe=0, haber=0):
    """Agrega una línea debe/haber a una partida."""
    cuenta = _obtener_cuenta(db, codigo_cuenta)
    linea = DetallePartida(
        idpartida = partida.idpartida,
        idcuenta  = cuenta.id,
        debe      = debe,
        haber     = haber,
    )
    db.add(linea)


def registrar_transaccion(datos: dict, db: Session):
    """
    Recibe los datos de una transacción, la guarda
    y genera automáticamente su partida de libro diario.
    """
    tipo       = datos.get("tipo", "").upper()
    monto_base = float(datos.get("monto_base", 0))
    con_iva    = datos.get("con_iva", True)
    iva        = round(monto_base * TASA_IVA, 2) if con_iva else 0

    # 1. Guardar la transacción
    tx = Transaccion(
        idperiodo     = datos["idperiodo"],
        fecha         = datos.get("fecha", date.today()),
        tipo          = tipo,
        descripcion   = datos["descripcion"],
        monto_base    = monto_base,
        iva           = iva,
        documento_ref = datos.get("documento_ref"),
    )
    db.add(tx)
    db.flush()

    total = monto_base + iva

    # 2. Generar la partida según el tipo de transacción
    if tipo == "VENTA":
        # El cliente paga → entra efectivo a Caja
        # Se genera IVA Débito Fiscal (deuda con la SAT)
        partida = _crear_partida(db, tx, f"Venta: {tx.descripcion}")
        _linea(db, partida, "1.1.1", debe=total)            # Caja (debe)
        _linea(db, partida, "4.1.1", haber=monto_base)      # Ventas (haber)
        _linea(db, partida, "2.1.2", haber=iva)             # IVA Débito Fiscal (haber)

    elif tipo == "COMPRA":
        # Se compra mercadería → entra al inventario
        # Se genera IVA Crédito Fiscal (derecho a deducir)
        partida = _crear_partida(db, tx, f"Compra: {tx.descripcion}")
        _linea(db, partida, "1.1.4", debe=monto_base)       # Inventario (debe)
        _linea(db, partida, "1.1.5", debe=iva)              # IVA Crédito Fiscal (debe)
        _linea(db, partida, "2.1.1", haber=total)           # Cuentas por Pagar (haber)

    elif tipo == "GASTO":
        # Se paga un gasto operativo (sueldos, luz, agua, etc.)
        codigo_gasto = datos.get("codigo_cuenta_gasto", "5.2.1")
        partida = _crear_partida(db, tx, f"Gasto: {tx.descripcion}")
        _linea(db, partida, codigo_gasto, debe=monto_base)  # Cuenta de Gasto (debe)
        _linea(db, partida, "1.1.5",      debe=iva)         # IVA Crédito Fiscal (debe)
        _linea(db, partida, "1.1.1",      haber=total)      # Caja (haber)

    elif tipo == "PAGO":
        # Se paga una cuenta por pagar (a un proveedor)
        partida = _crear_partida(db, tx, f"Pago: {tx.descripcion}")
        _linea(db, partida, "2.1.1", debe=total)            # Cuentas por Pagar (debe)
        _linea(db, partida, "1.1.1", haber=total)           # Caja (haber)

    elif tipo == "COBRO":
        # Se cobra una cuenta por cobrar (de un cliente)
        partida = _crear_partida(db, tx, f"Cobro: {tx.descripcion}")
        _linea(db, partida, "1.1.1", debe=total)            # Caja (debe)
        _linea(db, partida, "1.1.3", haber=total)           # Cuentas por Cobrar (haber)

    db.commit()
    db.refresh(tx)
    return {"transaccion": tx.idtransaccion, "partida": partida.numero_partida}
