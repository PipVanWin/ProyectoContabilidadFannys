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

router = APIRouter()

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
