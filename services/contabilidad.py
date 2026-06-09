"""
Lógica central del sistema contable: convierte una transacción
en una partida de Libro Diario con partida doble automática.

Este módulo es la implementación original de la lógica contable.
La versión extendida y orientada a objetos se encuentra en
services/transaccion_service.py (TransaccionService).

Reglas contables aplicadas (plan de cuentas guatemalteco):
  VENTA  → Debe: Caja (1.1.1)
            Haber: Ventas (4.1.1) + IVA Débito Fiscal (2.1.2)

  COMPRA → Debe: Inventario (1.1.4) + IVA Crédito Fiscal (1.1.5)
            Haber: Cuentas por Pagar (2.1.1)

  GASTO  → Debe: Cuenta de Gasto + IVA Crédito Fiscal (1.1.5)
            Haber: Caja (1.1.1)

  PAGO   → Debe: Cuentas por Pagar (2.1.1)
            Haber: Caja (1.1.1)

  COBRO  → Debe: Caja (1.1.1)
            Haber: Cuentas por Cobrar (1.1.3)

Tasa IVA aplicada: 12% (TASA_IVA definida en config.py)
"""

from sqlalchemy.orm import Session
from models.models import (
    Transaccion, PartidaDiaria, DetallePartida, CuentaContable, PeriodoContable
)
from config import TASA_IVA
from datetime import date


def _obtener_cuenta(db: Session, codigo: str) -> CuentaContable:
    """
    Busca una cuenta contable por su código en el catálogo.

    Args:
        db (Session): Sesión de base de datos.
        codigo (str): Código de la cuenta (ej. '1.1.1', '4.1.1').

    Raises:
        ValueError: Si el código no existe en el catálogo de cuentas.

    Returns:
        CuentaContable: Objeto de la cuenta contable encontrada.
    """
    cuenta = db.query(CuentaContable).filter_by(codigo=codigo).first()
    if not cuenta:
        raise ValueError(f"Cuenta {codigo} no encontrada en el catálogo")
    return cuenta


def _siguiente_numero_partida(db: Session, idperiodo: int) -> int:
    """
    Calcula el número correlativo de la siguiente partida del período.

    Args:
        db (Session): Sesión de base de datos.
        idperiodo (int): ID del período contable activo.

    Returns:
        int: Número de la siguiente partida (último número + 1).
    """
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
    """
    Crea el encabezado de una partida en el Libro Diario.

    Asigna automáticamente el número correlativo dentro del período
    y hace flush para obtener el idpartida antes del commit.

    Args:
        db (Session): Sesión de base de datos.
        transaccion (Transaccion): Transacción origen de la partida.
        concepto (str): Descripción del asiento contable.
        tipo (str): Tipo de partida ('NORMAL', 'CIERRE', etc.).
            Default: 'NORMAL'.

    Returns:
        PartidaDiaria: Objeto de la partida creada con su ID asignado.
    """
    num = _siguiente_numero_partida(db, transaccion.idperiodo)
    partida = PartidaDiaria(
        idtransaccion  = transaccion.idtransaccion,
        numero_partida = num,
        fecha          = transaccion.fecha,
        concepto       = concepto,
        tipo_partida   = tipo,
    )
    db.add(partida)
    db.flush()  
    return partida


def _linea(db, partida, codigo_cuenta, debe=0, haber=0):
    """
    Agrega una línea de débito o crédito a una partida del Libro Diario.

    Args:
        db (Session): Sesión de base de datos.
        partida (PartidaDiaria): Partida a la que pertenece la línea.
        codigo_cuenta (str): Código de la cuenta contable a afectar.
        debe (float): Monto al debe (default: 0).
        haber (float): Monto al haber (default: 0).

    Raises:
        ValueError: Si el código de cuenta no existe en el catálogo.
    """
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
    Registra una transacción y genera su partida doble en el Libro Diario.

    Proceso:
      1. Calcula el IVA automáticamente (12%) si aplica según el tipo.
      2. Guarda la transacción en la base de datos.
      3. Genera el asiento contable con partida doble según el tipo.

    Tipos soportados y su asiento:
      - VENTA:  Caja (D) | Ventas + IVA Débito (H)
      - COMPRA: Inventario + IVA Crédito (D) | Cuentas por Pagar (H)
      - GASTO:  Cuenta Gasto + IVA Crédito (D) | Caja (H)
      - PAGO:   Cuentas por Pagar (D) | Caja (H)
      - COBRO:  Caja (D) | Cuentas por Cobrar (H)

    Args:
        datos (dict): Diccionario con los datos de la transacción:
            - idperiodo (int): ID del período contable.
            - tipo (str): Tipo de transacción (VENTA/COMPRA/GASTO/PAGO/COBRO).
            - descripcion (str): Descripción del movimiento.
            - monto_base (float): Monto sin IVA.
            - con_iva (bool, opcional): Si se calcula IVA (default: True).
            - fecha (date, opcional): Fecha (default: hoy).
            - documento_ref (str, opcional): Referencia de documento.
            - codigo_cuenta_gasto (str, opcional): Código de cuenta de gasto
              para transacciones tipo GASTO (default: '5.2.1').
        db (Session): Sesión de base de datos.

    Returns:
        dict: Diccionario con:
            - transaccion (int): ID de la transacción creada.
            - partida (int): Número correlativo de la partida generada.
    """
    tipo       = datos.get("tipo", "").upper()
    monto_base = float(datos.get("monto_base", 0))
    con_iva    = datos.get("con_iva", True)
    iva        = round(monto_base * TASA_IVA, 2) if con_iva else 0

    # Guardar la transacción principal
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

    # Generar partida doble según tipo de transacción
    if tipo == "VENTA":
        # El cliente paga → entra efectivo a Caja
        # Se genera IVA Débito Fiscal (obligación con la SAT)
        partida = _crear_partida(db, tx, f"Venta: {tx.descripcion}")
        _linea(db, partida, "1.1.1", debe=total)            
        _linea(db, partida, "4.1.1", haber=monto_base)      
        _linea(db, partida, "2.1.2", haber=iva)           

    elif tipo == "COMPRA":
        # Se compra mercadería → entra al inventario
        # Se genera IVA Crédito Fiscal 
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
        # Se cancela una cuenta por pagar a un proveedor
        partida = _crear_partida(db, tx, f"Pago: {tx.descripcion}")
        _linea(db, partida, "2.1.1", debe=total)            # Cuentas por Pagar (debe)
        _linea(db, partida, "1.1.1", haber=total)           # Caja (haber)

    elif tipo == "COBRO":
        # Se cobra una cuenta pendiente de un cliente
        partida = _crear_partida(db, tx, f"Cobro: {tx.descripcion}")
        _linea(db, partida, "1.1.1", debe=total)            # Caja (debe)
        _linea(db, partida, "1.1.3", haber=total)           # Cuentas por Cobrar (haber)

    db.commit()
    db.refresh(tx)
    return {"transaccion": tx.idtransaccion, "partida": partida.numero_partida}
