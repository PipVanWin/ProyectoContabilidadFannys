# routers/inventario.py
# Endpoints para gestionar productos, insumos y activos fijos.

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.models import InventarioProducto, ActivoFijo, SaldoInicial

router = APIRouter()

@router.get("/productos")
def listar_productos(db: Session = Depends(get_db)):
    """Lista todos los productos/insumos del inventario."""
    return db.query(InventarioProducto).filter_by(activo=True).all()

@router.get("/activos")
def listar_activos(db: Session = Depends(get_db)):
    """Lista todos los activos fijos (terrenos, vehículos, mobiliario, etc.)."""
    return db.query(ActivoFijo).filter_by(activo=True).all()

@router.get("/saldos-iniciales/{idperiodo}")
def saldos_iniciales(idperiodo: int, db: Session = Depends(get_db)):
    """Retorna el balance de apertura de un período."""
    return db.query(SaldoInicial).filter_by(idperiodo=idperiodo).all()
