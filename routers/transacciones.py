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

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

@router.get("/")
def transacciones_page(request: Request, db: Session = Depends(get_db)):
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
    cuentas = (
        db.query(CuentaContable)
        .filter_by(tipo="Gasto", activa=True)
        .order_by(CuentaContable.codigo)
        .all()
    )
    return [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre} for c in cuentas]

@router.get("/{idperiodo}")
def listar_transacciones(idperiodo: int, db: Session = Depends(get_db)):
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
    
