"""
Controlador HTTP para el módulo de Transacciones.

Gestiona el registro, consulta y anulación de movimientos financieros
(ventas, compras, gastos y pagos) del período contable activo.
Cada transacción genera automáticamente su asiento en el Libro Diario
y calcula el IVA correspondiente (12%) según la legislación guatemalteca.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from database import get_db
from models.models import CuentaContable, PeriodoContable, Transaccion
from schemas.schemas import TransaccionCreate
from services.transaccion_service import TransaccionService

router = APIRouter()

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Lista de meses 
MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


@router.get("/")
def transacciones_page(request: Request, db: Session = Depends(get_db)):
    """
    Muestra la página principal del módulo de transacciones.

    Carga y lista todas las transacciones no anuladas del período activo
    (estado='ABIERTO'). Si no existe un período abierto, muestra el
    período más reciente disponible como fallback.

    Args:
        request (Request): Objeto de solicitud HTTP de FastAPI/Starlette.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        TemplateResponse: Renderiza 'transacciones.html' con la lista
        de transacciones y los datos del período actual.
    """
    periodo = (
        db.query(PeriodoContable)
        .filter_by(estado="ABIERTO")
        .first()
    ) or (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .first()
    )
    txs = db.query(Transaccion).filter_by(
        idperiodo=periodo.idperiodo, anulada=False
    ).order_by(Transaccion.fecha).all() if periodo else []
    return templates.TemplateResponse(
        request=request,
        name="transacciones.html",
        context={
            "transacciones": txs,
            "periodo": f"{MESES[periodo.mes]}-{periodo.anio}" if periodo else "—",
            "estado": periodo.estado if periodo else "—",
            "active": "transacciones",
        }
    )


@router.get("/nueva")
def nueva_transaccion(request: Request, db: Session = Depends(get_db)):
    """
    Muestra el formulario para registrar una nueva transacción.

    Obtiene el período contable activo para asociar la nueva transacción.
    Si no hay período abierto, usa el más reciente como referencia.

    Args:
        request (Request): Objeto de solicitud HTTP de FastAPI/Starlette.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        TemplateResponse: Renderiza 'nueva_transaccion.html' con el
        contexto del período activo (nombre, estado e ID).
    """
    periodo = (
        db.query(PeriodoContable)
        .filter_by(estado="ABIERTO")
        .first()
    ) or (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .first()
    )
    return templates.TemplateResponse(
        request=request,
        name="nueva_transaccion.html",
        context={
            "periodo": f"{MESES[periodo.mes]}-{periodo.anio}" if periodo else "—",
            "estado": periodo.estado if periodo else "—",
            "idperiodo": periodo.idperiodo if periodo else 1,
            "active": "transacciones",
        }
    )


@router.get("/cuentas/gasto")
def listar_cuentas_gasto(db: Session = Depends(get_db)):
    """
    Retorna el catálogo de cuentas contables de tipo 'Gasto' activas.

    Endpoint consumido por el frontend (JavaScript) para poblar el
    selector de cuentas de gasto al momento de registrar una transacción
    de tipo GASTO.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[dict]: Lista de cuentas con sus campos id, codigo y nombre,
        ordenadas por código contable ascendente.
    """
    cuentas = (
        db.query(CuentaContable)
        .filter_by(tipo="Gasto", activa=True)
        .order_by(CuentaContable.codigo)
        .all()
    )
    return [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre} for c in cuentas]


@router.get("/{idperiodo}")
def listar_transacciones(idperiodo: int, db: Session = Depends(get_db)):
    """
    Retorna en formato JSON todas las transacciones de un período específico.

    Endpoint de API utilizado para consultar transacciones por período,
    útil para reportes e historial contable. Solo retorna transacciones
    no anuladas, ordenadas por fecha e ID.

    Args:
        idperiodo (int): ID del período contable a consultar.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (404): Si el período especificado no existe en la BD.

    Returns:
        list[dict]: Lista de transacciones con fecha, tipo, descripción,
        monto base, IVA, total y referencia de documento.
    """
    periodo = db.query(PeriodoContable).get(idperiodo)
    if not periodo:
        raise HTTPException(status_code=404, detail="Período no encontrado.")
    txs = (
        db.query(Transaccion)
        .filter_by(idperiodo=idperiodo, anulada=False)
        .order_by(Transaccion.fecha, Transaccion.idtransaccion)
        .all()
    )
    return [
        {
            "idtransaccion": t.idtransaccion,
            "fecha":         str(t.fecha),
            "tipo":          t.tipo,
            "descripcion":   t.descripcion,
            "monto_base":    float(t.monto_base),
            "iva":           float(t.iva),
            "total":         float(t.total),
            "documento_ref": t.documento_ref,
        }
        for t in txs
    ]


@router.post("/")
def crear_transaccion(datos: dict, db: Session = Depends(get_db)):
    """
    Registra una nueva transacción financiera en el sistema.

    Recibe los datos del formulario, calcula automáticamente el IVA si no
    se proporciona (12% para VENTA, COMPRA y GASTO), valida la estructura
    con el schema TransaccionCreate y delega la lógica de negocio al
    TransaccionService, que genera el asiento contable correspondiente.

    Tipos de transacción soportados:
        - VENTA:  Genera IVA Débito Fiscal (12%).
        - COMPRA: Genera IVA Crédito Fiscal (12%).
        - GASTO:  Genera IVA Crédito Fiscal (12%).
        - PAGO:   Sin cálculo de IVA.

    Args:
        datos (dict): Cuerpo de la solicitud con los campos:
            - idperiodo (int): ID del período contable.
            - fecha (date): Fecha de la transacción.
            - tipo (str): Tipo de transacción (VENTA/COMPRA/GASTO/PAGO).
            - descripcion (str): Descripción del movimiento.
            - monto_base (float): Monto sin IVA.
            - iva (float, opcional): Si se omite, se calcula automáticamente.
            - documento_ref (str, opcional): Número de factura o referencia.
            - detalles (list, opcional): Detalles del asiento contable.
            - id_cuenta_gasto (int, opcional): Cuenta contable para gastos.
            - forma_pago (str): Medio de pago (default: 'CAJA').
            - id_cuenta_pagocobro (int, opcional): Cuenta de pago/cobro.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (400): Si los datos son inválidos (ValueError).
        HTTPException (500): Si ocurre un error inesperado en el servidor.

    Returns:
        dict: Confirmación con los datos de la transacción creada:
        ok, idtransaccion, tipo, monto_base, iva y total.
    """
    try:
        monto_base = float(datos.get("monto_base", 0))
        tipo       = datos.get("tipo", "").upper()
        TIPOS_CON_IVA = {"VENTA", "COMPRA", "GASTO"}
        if "iva" not in datos or datos["iva"] is None:
            datos["iva"] = round(monto_base * 0.12, 2) if tipo in TIPOS_CON_IVA else 0
        data = TransaccionCreate(
            idperiodo     = datos["idperiodo"],
            fecha         = datos.get("fecha", date.today()),
            tipo          = tipo,
            descripcion   = datos["descripcion"],
            monto_base    = monto_base,
            iva           = datos["iva"],
            documento_ref = datos.get("documento_ref"),
            detalles      = datos.get("detalles", []),
        )
        id_cuenta_gasto  = datos.get("id_cuenta_gasto")
        forma_pago       = datos.get("forma_pago", "CAJA")
        cuenta_pagocobro = datos.get("id_cuenta_pagocobro")
        tx = TransaccionService.crear_transaccion(
            db, data,
            id_cuenta_gasto=id_cuenta_gasto,
            forma_pago=forma_pago,
            cuenta_pagocobro=cuenta_pagocobro
        )
        return {
            "ok":            True,
            "idtransaccion": tx.idtransaccion,
            "tipo":          tx.tipo,
            "monto_base":    float(tx.monto_base),
            "iva":           float(tx.iva),
            "total":         float(tx.total),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")


@router.post("/{idtransaccion}/anular")
def anular_transaccion(idtransaccion: int, datos: dict, db: Session = Depends(get_db)):
    """
    Anula una transacción existente sin eliminarla físicamente de la BD.

    La anulación es un proceso lógico: la transacción queda marcada como
    anulada (anulada=True) junto con el motivo registrado. Esto preserva
    la integridad del historial contable y permite auditoría posterior.

    Args:
        idtransaccion (int): ID de la transacción a anular.
        datos (dict): Cuerpo de la solicitud con:
            - motivo (str, opcional): Razón de la anulación.
              Default: 'Sin motivo especificado'.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (400): Si la transacción no puede anularse
        (ej. ya está anulada o pertenece a un período cerrado).

    Returns:
        dict: Confirmación con idtransaccion, estado anulada y mensaje.
    """
    motivo = datos.get("motivo", "Sin motivo especificado")
    try:
        tx = TransaccionService.anular_transaccion(db, idtransaccion, motivo)
        return {
            "ok":            True,
            "idtransaccion": tx.idtransaccion,
            "anulada":       tx.anulada,
            "mensaje":       f"Transacción {idtransaccion} anulada correctamente.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
