from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models.models import PeriodoContable, Transaccion, PartidaDiaria, DetallePartida, CuentaContable, DetalleTransaccion
from datetime import date

router = APIRouter()
BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

@router.get("/")
def historial_page(request: Request, db: Session = Depends(get_db)):
    periodos = (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .all()
    )
    resumen = []
    for p in periodos:
        txs = db.query(Transaccion).filter_by(
            idperiodo=p.idperiodo, anulada=False
        ).filter(Transaccion.tipo != "CIERRE").all()

        ingresos = sum(float(t.monto_base) for t in txs if t.tipo == "VENTA")
        gastos   = sum(float(t.monto_base) for t in txs if t.tipo in ("COMPRA", "GASTO", "PAGO"))

        resumen.append({
            "idperiodo": p.idperiodo,
            "nombre":    f"{MESES[p.mes]}-{p.anio}",
            "estado":    p.estado,
            "ingresos":  ingresos,
            "gastos":    gastos,
            "utilidad":  ingresos - gastos,
        })

    periodo_activo = (
        db.query(PeriodoContable).filter_by(estado="ABIERTO").first()
    ) or (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .first()
    )

    return templates.TemplateResponse(
        request=request,
        name="historial.html",
        context={
            "periodos":    resumen,
            "active":      "historial",
            "periodo":     f"{MESES[periodo_activo.mes]}-{periodo_activo.anio}" if periodo_activo else "—",
            "estado":      periodo_activo.estado if periodo_activo else "—",
            "anio_actual": date.today().year,
        }
    )

@router.post("/reset")
def reset_periodo(datos: dict, db: Session = Depends(get_db)):
    mes  = int(datos.get("mes", 0))
    anio = int(datos.get("anio", 0))
    if not mes or not anio:
        raise HTTPException(status_code=400, detail="Mes y año son requeridos")

    # Verificar que no exista ya ese período
    empresa = db.query(PeriodoContable).first()
    from models.models import Empresa
    empresa_obj = db.query(Empresa).first()

    existente = db.query(PeriodoContable).filter_by(
        mes=mes, anio=anio
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"El período {MESES[mes]}-{anio} ya existe")

    # Crear período nuevo
    nuevo = PeriodoContable(
        id_empresa = empresa_obj.id_empresa,
        mes        = mes,
        anio       = anio,
        estado     = "ABIERTO"
    )
    db.add(nuevo)
    db.commit()

    return {"ok": True, "mensaje": f"Período {MESES[mes]}-{anio} abierto correctamente"}