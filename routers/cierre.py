"""
Controlador HTTP para el módulo de Cierre Contable Mensual.

Al ejecutarse, dispara automáticamente el proceso completo de
corte mensual en el siguiente orden:
  1. Regularización del IVA (Débito vs Crédito Fiscal)
  2. Cierre de ingresos
  3. Cierre de gastos
  4. Cierre a capital

Toda la lógica contable del cierre vive en services/cierre.py.
Este router solo valida el estado del período y delega la ejecución.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from database import get_db
from models.models import PeriodoContable
from services.cierre import ejecutar_cierre_mensual

router = APIRouter()
BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Lista de meses
MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


@router.get("/")
def cierre_page(request: Request, db: Session = Depends(get_db)):
    """
    Muestra la página del módulo de cierre contable.

    Carga el período activo (estado='ABIERTO') para mostrar cuál
    es el período que está próximo a cerrarse. Si no hay período
    abierto, usa el más reciente como referencia.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        TemplateResponse: Renderiza 'cierre.html' con el nombre,
        estado e ID del período activo para confirmar el cierre.
    """
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
            "periodo":   f"{MESES[periodo.mes]}-{periodo.anio}" if periodo else "—",
            "estado":    periodo.estado if periodo else "—",
            "idperiodo": periodo.idperiodo if periodo else None,
            "active":    "cierre",
        }
    )


@router.post("/{idperiodo}")
def cerrar_periodo(idperiodo: int, db: Session = Depends(get_db)):
    """
    Ejecuta el cierre contable completo del período indicado.

    Valida que el período exista y esté en estado 'ABIERTO' antes
    de ejecutar el proceso. Una vez validado, delega toda la lógica
    contable a ejecutar_cierre_mensual() en services/cierre.py, que
    genera automáticamente las partidas de:
      - Regularización del IVA
      - Cierre de ingresos
      - Cierre de gastos
      - Cierre a capital

    El período queda en estado 'CERRADO' al finalizar el proceso
    y no puede recibir nuevas transacciones.

    Args:
        idperiodo (int): ID del período contable a cerrar.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (404): Si el período no existe.
        HTTPException (400): Si el período ya está cerrado.

    Returns:
        dict: Resultado del cierre generado por ejecutar_cierre_mensual().
    """
    periodo = db.query(PeriodoContable).get(idperiodo)
    if not periodo:
        raise HTTPException(status_code=404, detail="Período no encontrado")
    if periodo.estado == "CERRADO":
        raise HTTPException(status_code=400, detail="El período ya está cerrado")

    return ejecutar_cierre_mensual(periodo, db)
