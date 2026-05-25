# routers/reportes.py
# Endpoints que generan los reportes contables del período:
# libro diario, libro mayor y estado de resultados.
# Usan las vistas SQL que ya están en ContabilidadGT.

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models.models import PartidaDiaria, Transaccion, PeriodoContable, Empresa, DetallePartida
router = APIRouter()
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/libro-diario")
def libro_diario(request: Request, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    periodo = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    partidas = (
        db.query(PartidaDiaria)
        .join(Transaccion)
        .filter(Transaccion.idperiodo == periodo.idperiodo)
        .options(
            joinedload(PartidaDiaria.detalles)
            .joinedload(DetallePartida.cuenta),
            joinedload(PartidaDiaria.transaccion)
        )
        .order_by(PartidaDiaria.numero_partida)
        .all()
    )

    return templates.TemplateResponse(
    request=request,
    name="libro_diario.html",
    context={
        "partidas": partidas,
        "periodo":  f"MAY-{periodo.anio}" if periodo else "—",
        "estado":   periodo.estado if periodo else "—",
        "active":   "diario",
    }
)
