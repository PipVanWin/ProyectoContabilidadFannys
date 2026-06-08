# routers/cierre.py
# Endpoint del corte mensual automático.
# Al llamarlo ejecuta en orden:
#   1. Regularización del IVA
#   2. Cierre de ingresos
#   3. Cierre de gastos
#   4. Cierre a capital
# Toda la lógica vive en services/cierre.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.models import PeriodoContable
from services.cierre import ejecutar_cierre_mensual
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()
BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

@router.get("/")
def cierre_page(request: Request, db: Session = Depends(get_db)):
    periodo = (
    db.query(PeriodoContable).filter_by(estado="ABIERTO").first()
) or (
    db.query(PeriodoContable)
    .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
    .first()
)
    return templates.TemplateResponse(
        request=request,
        name="cierre.html",
        context={
            "periodo": f"{MESES[periodo.mes]}-{periodo.anio}" if periodo else "—",
            "estado": periodo.estado if periodo else "—",
            "idperiodo": periodo.idperiodo if periodo else None,
            "active": "cierre",
        }
    )

@router.post("/{idperiodo}")
def cerrar_periodo(idperiodo: int, db: Session = Depends(get_db)):
    """
    Ejecuta el cierre contable completo del período.
    Solo puede ejecutarse si el período está ABIERTO.
    """
    periodo = db.query(PeriodoContable).get(idperiodo)
    if not periodo:
        raise HTTPException(status_code=404, detail="Período no encontrado")
    if periodo.estado == "CERRADO":
        raise HTTPException(status_code=400, detail="El período ya está cerrado")
    return ejecutar_cierre_mensual(periodo, db)
