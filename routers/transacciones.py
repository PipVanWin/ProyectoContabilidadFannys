# routers/transacciones.py
# Endpoints para registrar transacciones del mes.
# Cada transacción genera automáticamente su partida en el libro diario.
# (La lógica de generación vive en services/contabilidad.py)

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models.models import Transaccion, PeriodoContable
from pathlib import Path

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/nueva")
def nueva_transaccion(request: Request, db: Session = Depends(get_db)):
    # pendiente de implementar
    pass

@router.get("/{idperiodo}")
def listar_transacciones(idperiodo: int, db: Session = Depends(get_db)):
    """Lista todas las transacciones de un período."""
    return db.query(Transaccion).filter_by(idperiodo=idperiodo, anulada=False).all()

@router.post("/")
def crear_transaccion(datos: dict, db: Session = Depends(get_db)):
    """
    Registra una transacción y genera su partida contable automáticamente.
    La lógica de partida doble vive en services/contabilidad.py
    """
    return registrar_transaccion(datos, db)
