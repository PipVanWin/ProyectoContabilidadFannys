# services/transaccion_service.py
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
        cuenta = db.query(CuentaContable).filter_by(codigo=codigo).first()
        if not cuenta:
            raise ValueError(f"Cuenta {codigo} no encontrada en el catálogo")
        return cuenta

    @staticmethod
    def _siguiente_numero_partida(db: Session, idperiodo: int) -> int:
        ultimo = (
            db.query(func.max(PartidaDiaria.numero_partida))
            .join(Transaccion)
            .filter(Transaccion.idperiodo == idperiodo)
            .scalar()
        )
        return (ultimo or 0) + 1

    @staticmethod
    def _agregar_linea(db, partida, cuenta, debe=0, haber=0):
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
        id_cuenta_gasto: int = None
    ) -> Transaccion:

        # 1. Guardar la transacción
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

        # 2. Guardar detalles si los hay
        for det in data.detalles:
            d = DetalleTransaccion(
                idtransaccion   = tx.idtransaccion,
                idproducto      = det.idproducto,
                descripcion     = det.descripcion,
                cantidad        = det.cantidad,
                precio_unitario = det.precio_unitario,
            )
            db.add(d)

        # 3. Crear partida del libro diario
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

        # 4. Generar partida doble según tipo
        if data.tipo == "VENTA":
            caja    = cls._obtener_cuenta(db, "1.1.1")
            ventas  = cls._obtener_cuenta(db, "4.1.1")
            iva_deb = cls._obtener_cuenta(db, "2.1.2")
            cls._agregar_linea(db, partida, caja,    debe=total)
            cls._agregar_linea(db, partida, ventas,  haber=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_deb, haber=float(data.iva))

        elif data.tipo == "COMPRA":
            inventario = cls._obtener_cuenta(db, "1.1.4")
            iva_cred   = cls._obtener_cuenta(db, "1.1.5")
            cxp        = cls._obtener_cuenta(db, "2.1.1")
            cls._agregar_linea(db, partida, inventario, debe=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_cred,   debe=float(data.iva))
            cls._agregar_linea(db, partida, cxp,        haber=total)

        elif data.tipo == "GASTO":
            if not id_cuenta_gasto:
                raise ValueError("Se requiere id_cuenta_gasto para registrar un gasto")
            cuenta_gasto = db.query(CuentaContable).get(id_cuenta_gasto)
            if not cuenta_gasto:
                raise ValueError(f"Cuenta de gasto {id_cuenta_gasto} no encontrada")
            iva_cred = cls._obtener_cuenta(db, "1.1.5")
            caja     = cls._obtener_cuenta(db, "1.1.1")
            cls._agregar_linea(db, partida, cuenta_gasto, debe=float(data.monto_base))
            cls._agregar_linea(db, partida, iva_cred,     debe=float(data.iva))
            cls._agregar_linea(db, partida, caja,         haber=total)

        elif data.tipo == "PAGO":
            cxp  = cls._obtener_cuenta(db, "2.1.1")
            caja = cls._obtener_cuenta(db, "1.1.1")
            cls._agregar_linea(db, partida, cxp,  debe=total)
            cls._agregar_linea(db, partida, caja, haber=total)

        elif data.tipo == "COBRO":
            caja = cls._obtener_cuenta(db, "1.1.1")
            cxc  = cls._obtener_cuenta(db, "1.1.3")
            cls._agregar_linea(db, partida, caja, debe=total)
            cls._agregar_linea(db, partida, cxc,  haber=total)

        db.commit()
        db.refresh(tx)
        return tx

    @classmethod
    def anular_transaccion(cls, db: Session, idtransaccion: int, motivo: str) -> Transaccion:
        tx = db.query(Transaccion).get(idtransaccion)
        if not tx:
            raise ValueError(f"Transacción {idtransaccion} no encontrada")
        if tx.anulada:
            raise ValueError(f"La transacción {idtransaccion} ya está anulada")
        tx.anulada = True
        db.commit()
        db.refresh(tx)
        return tx