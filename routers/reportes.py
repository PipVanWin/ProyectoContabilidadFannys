# routers/reportes.py
# Endpoints que generan los reportes contables del período:
# libro diario, libro mayor y estado de resultados.
# Usan las vistas SQL que ya están en ContabilidadGT.

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter()

@router.get("/libro-diario/{idperiodo}")
def libro_diario(idperiodo: int, db: Session = Depends(get_db)):
    """Retorna todas las partidas del libro diario del período."""
    resultado = db.execute(
        text("SELECT * FROM vw_LibroDiario WHERE mes = :mes"),
        {"mes": idperiodo}
    )
    return resultado.mappings().all()

@router.get("/libro-mayor/{idperiodo}")
def libro_mayor(idperiodo: int, db: Session = Depends(get_db)):
    """Retorna el saldo de cada cuenta contable del período."""
    resultado = db.execute(
        text("SELECT * FROM vw_LibroMayor WHERE idperiodo = :id"),
        {"id": idperiodo}
    )
    return resultado.mappings().all()

@router.get("/estado-resultados/{idperiodo}")
def estado_resultados(idperiodo: int, db: Session = Depends(get_db)):
    """Retorna ingresos y gastos del período para el estado de resultados."""
    resultado = db.execute(
        text("SELECT * FROM vw_EstadoResultados WHERE idperiodo = :id"),
        {"id": idperiodo}
    )
    return resultado.mappings().all()

@router.get("/iva/{idperiodo}")
def regularizacion_iva(idperiodo: int, db: Session = Depends(get_db)):
    """Retorna el cálculo de IVA débito, crédito y neto a pagar."""
    resultado = db.execute(
        text("SELECT * FROM vw_RegularizacionIVA WHERE idperiodo = :id"),
        {"id": idperiodo}
    )
    return resultado.mappings().all()
