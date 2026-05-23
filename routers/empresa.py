# routers/empresa.py
# Endpoints relacionados con la empresa y períodos contables.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.models import Empresa, PeriodoContable

router = APIRouter()

@router.get("/")
def obtener_empresa(db: Session = Depends(get_db)):
    """Retorna los datos de Fannys Express."""
    empresa = db.query(Empresa).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa

@router.get("/periodos")
def listar_periodos(db: Session = Depends(get_db)):
    """Lista todos los períodos contables registrados."""
    return db.query(PeriodoContable).all()

@router.post("/periodos")
def crear_periodo(mes: int, anio: int, db: Session = Depends(get_db)):
    """Abre un nuevo período contable para el mes y año indicados."""
    empresa = db.query(Empresa).first()
    existente = db.query(PeriodoContable).filter_by(
        id_empresa=empresa.id_empresa, mes=mes, anio=anio
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="El período ya existe")
    periodo = PeriodoContable(id_empresa=empresa.id_empresa, mes=mes, anio=anio)
    db.add(periodo)
    db.commit()
    db.refresh(periodo)
    return periodo
