"""
Servicio de lógica de negocio para el registro de transacciones.

Implementa la partida doble contable automática según el tipo de
transacción. Cada operación registrada genera su asiento en el
Libro Diario con los débitos y créditos correspondientes,
siguiendo el plan de cuentas guatemalteco del sistema.

Cuentas del plan contable utilizadas:
  1.1.1 — Caja
  1.1.2 — Bancos
  1.1.3 — Clientes (Cuentas por Cobrar)
  1.1.4 — Inventario
  1.1.5 — IVA Crédito Fiscal
  2.1.1 — Proveedores (Cuentas por Pagar)
  2.1.2 — IVA Débito Fiscal
  4.1.1 — Ventas
"""

from datetime import date
from sqlalchemy.orm import Session
from models.models import (
    Transaccion, PartidaDiaria, DetallePartida,
    DetalleTransaccion, CuentaContable, PeriodoContable
)
from schemas.schemas import TransaccionCreate
from sqlalchemy import func


class TransaccionService:

    @staticmethod
    def _obtener_cuenta(db: Session, codigo: str) -> CuentaContable:
        """
        Busca y retorna una cuenta contable por su código.

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

    @staticmethod
    def _siguiente_numero_partida(db: Session, idperiodo: int) -> int:
        """
        Calcula el número correlativo de la siguiente partida del período.

        Consulta el número máximo de partida existente en el período
        y retorna el siguiente en la secuencia.

        Args:
            db (Session): Sesión de base de datos.
            idperiodo (int): ID del período contable activo.

        Returns:
            int: Número correlativo de la siguiente partida (último + 1).
        """
        ultimo = (
            db.query(func.max(PartidaDiaria.numero_partida))
            .join(Transaccion)
            .filter(Transaccion.idperiodo == idperiodo)
            .scalar()
        )
        return (ultimo or 0) + 1

    @staticmethod
    def _agregar_linea(db, partida, cuenta, debe=0, haber=0):
        """
        Agrega una línea de débito o crédito a una partida del Libro Diario.

        Crea un DetallePartida que representa una línea del asiento
        contable, asociada a una cuenta específica con su monto de
        debe y/o haber.

        Args:
            db (Session): Sesión de base de datos.
            partida (PartidaDiaria): Partida a la que pertenece la línea.
            cuenta (CuentaContable): Cuenta contable afectada.
            debe (float): Monto al debe (default: 0).
            haber (float): Monto al haber (default: 0).
        """
        linea = DetallePartida(
            idpartida = partida.idpartida,
            idcuenta  = cuenta.id,
            debe      = debe,
            haber     = haber,
        )
        db.add(linea)

    @classmethod
    def crear_transaccion(
        cls,
        db: Session,
        data: TransaccionCreate,
        id_cuenta_gasto: int = None,
        forma_pago: str = "CAJA",
        cuenta_pagocobro: str = None,
    ) -> Transaccion:
        """
        Registra una transacción financiera y genera su asiento contable.

        Ejecuta el proceso completo en 4 pasos:
          1. Determina la cuenta de dinero según la forma de pago.
          2. Guarda la transacción y sus detalles de productos.
          3. Crea la partida en el Libro Diario con número correlativo.
          4. Genera la partida doble según el tipo de transacción:

        Partidas dobles generadas por tipo:
          - VENTA:  Débito Caja/Banco/Clientes | Crédito Ventas + IVA Débito
          - COMPRA: Débito Inventario + IVA Crédito | Crédito Caja/Banco
          - GASTO:  Débito Cuenta Gasto + IVA Crédito | Crédito Caja/Banco
          - PAGO:   Débito Proveedores/CxP | Crédito Caja/Banco
          - COBRO:  Débito Caja/Banco | Crédito Clientes/CxC

        Args:
            db (Session): Sesión de base de datos.
            data (TransaccionCreate): Schema con los datos validados
                de la transacción (período, fecha, tipo, montos, etc.).
            id_cuenta_gasto (int, opcional): ID de la cuenta de gasto
                específica. Requerido cuando tipo='GASTO'.
            forma_pago (str): Medio de pago utilizado:
                - 'CAJA' → cuenta 1.1.1 (default)
                - 'BANCO' → cuenta 1.1.2
                - 'CREDITO' → cuenta 1.1.3 (ventas) o 2.1.1 (compras)
            cuenta_pagocobro (str, opcional): Código de cuenta alternativa
                para operaciones de PAGO o COBRO.

        Raises:
            ValueError: Si falta id_cuenta_gasto en transacciones de tipo GASTO.
            ValueError: Si alguna cuenta del plan contable no se encuentra.

        Returns:
            Transaccion: Objeto de la transacción creada y confirmada en BD.
        """
        # Determinar cuenta de dinero según forma de pago
        if forma_pago == "BANCO":
            cod_dinero = "1.1.2"
        elif forma_pago == "CREDITO":
            cod_dinero = "1.1.3" if data.tipo == "VENTA" else "2.1.1"
        else:
            cod_dinero = "1.1.1"  # CAJA por defecto
        cuenta_dinero = cls._obtener_cuenta(db, cod_dinero)

        # Guardar la transacción principal
        tx = Transaccion(
            idperiodo     = data.idperiodo,
            fecha         = data.fecha,
            tipo          = data.tipo,
            descripcion   = data.descripcion,
            monto_base    = data.monto_base,
            iva           = data.iva,
            documento_ref = data.documento_ref,
        )
        db.add(tx)
        db.flush()  

        total = float(data.monto_base) + float(data.iva)

        # Guardar detalles de productos si los hay
        for det in data.detalles:
            d = DetalleTransaccion(
                idtransaccion   = tx.idtransaccion,
                idproducto      = det.idproducto,
                descripcion     = det.descripcion,
                cantidad        = det.cantidad,
                precio_unitario = det.precio_unitario,
            )
            db.add(d)

        # Crear partida del Libro Diario con número correlativo
        num = cls._siguiente_numero_partida(db, data.idperiodo)
        partida = PartidaDiaria(
            idtransaccion  = tx.idtransaccion,
            numero_partida = num,
            fecha          = data.fecha,
            concepto       = data.descripcion,
            tipo_partida   = "NORMAL",
        )
        db.add(partida)
        db.flush() 

        # Generar partida doble según tipo de transacción
        if data.tipo == "VENTA":
            # Débito: Caja/Banco/Clientes (total con IVA)
            # Crédito: Ventas (monto base) + IVA Débito Fiscal
            ventas  = cls._obtener_cuenta(db, "4.1.1")
            iva_deb = cls._obtener_cuenta(db, "2.1.2")
            cls._agregar_linea(db, partida, cuenta_dinero, debe=total)
            cls._agregar_linea(db, partida, ventas,        haber=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_deb,       haber=float(data.iva))

        elif data.tipo == "COMPRA":
            # Débito: Inventario (monto base) + IVA Crédito Fiscal
            # Crédito: Caja/Banco (total con IVA)
            inventario = cls._obtener_cuenta(db, "1.1.4")
            iva_cred   = cls._obtener_cuenta(db, "1.1.5")
            cls._agregar_linea(db, partida, inventario,    debe=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_cred,      debe=float(data.iva))
            cls._agregar_linea(db, partida, cuenta_dinero, haber=total)

        elif data.tipo == "GASTO":
            # Débito: Cuenta de Gasto específica + IVA Crédito Fiscal
            # Crédito: Caja/Banco (total con IVA)
            if not id_cuenta_gasto:
                raise ValueError("Se requiere id_cuenta_gasto para registrar un gasto")
            cuenta_gasto = db.query(CuentaContable).get(id_cuenta_gasto)
            if not cuenta_gasto:
                raise ValueError(f"Cuenta de gasto {id_cuenta_gasto} no encontrada")
            iva_cred = cls._obtener_cuenta(db, "1.1.5")
            cls._agregar_linea(db, partida, cuenta_gasto,  debe=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_cred,      debe=float(data.iva))
            cls._agregar_linea(db, partida, cuenta_dinero, haber=total)

        elif data.tipo == "PAGO":
            # Débito: Proveedores/CxP (cancela la obligación)
            # Crédito: Caja/Banco (sale el dinero)
            cxp = cls._obtener_cuenta(db, cuenta_pagocobro) if cuenta_pagocobro else cls._obtener_cuenta(db, "2.1.1")
            cls._agregar_linea(db, partida, cxp,           debe=total)
            cls._agregar_linea(db, partida, cuenta_dinero, haber=total)

        elif data.tipo == "COBRO":
            # Débito: Caja/Banco (entra el dinero)
            # Crédito: Clientes/CxC (cancela la cuenta por cobrar)
            cxc = cls._obtener_cuenta(db, cuenta_pagocobro) if cuenta_pagocobro else cls._obtener_cuenta(db, "1.1.3")
            cls._agregar_linea(db, partida, cxc,           debe=total)
            cls._agregar_linea(db, partida, cuenta_dinero, haber=total)

        db.commit()
        db.refresh(tx)
        return tx

    @classmethod
    def anular_transaccion(cls, db: Session, idtransaccion: int, motivo: str) -> Transaccion:
        """
        Anula una transacción marcándola como inactiva (anulada=True).

        La anulación es lógica, no física: el registro permanece en la
        base de datos con el flag anulada=True para preservar el historial
        y permitir auditoría. Las transacciones anuladas se excluyen de
        todos los reportes y cálculos del sistema.

        Args:
            db (Session): Sesión de base de datos.
            idtransaccion (int): ID de la transacción a anular.
            motivo (str): Razón de la anulación (para registro de auditoría).

        Raises:
            ValueError: Si la transacción no existe.
            ValueError: Si la transacción ya fue anulada previamente.

        Returns:
            Transaccion: Objeto actualizado con anulada=True.
        """
        tx = db.query(Transaccion).get(idtransaccion)
        if not tx:
            raise ValueError(f"Transacción {idtransaccion} no encontrada")
        if tx.anulada:
            raise ValueError(f"La transacción {idtransaccion} ya está anulada")
        tx.anulada = True
        db.commit()
        db.refresh(tx)
        return tx
