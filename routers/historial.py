"""
Controlador HTTP para el módulo de Historial Contable.

Permite consultar el resumen financiero de todos los períodos
contables registrados (abiertos y cerrados), mostrando ingresos,
gastos y utilidad de cada uno. También permite crear nuevos
períodos contables manualmente cuando sea necesario.
"""

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

# Lista de meses 
MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


@router.get("/")
def historial_page(request: Request, db: Session = Depends(get_db)):
    """
    Muestra la página de historial con el resumen de todos los períodos.

    Recorre todos los períodos contables registrados y calcula para
    cada uno el total de ingresos (ventas), gastos (compras, gastos
    y pagos) y utilidad neta. Excluye transacciones anuladas y
    partidas de cierre contable del cálculo.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        TemplateResponse: Renderiza 'historial.html' con la lista de
        períodos y su resumen financiero (ingresos, gastos, utilidad,
        estado), más el período activo para el encabezado.
    """
    periodos = (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .all()
    )

    # Resumen financiero de cada período
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

    # Obtener período activo para el encabezado 
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
    """
    Crea un nuevo período contable con estado 'ABIERTO'.

    Valida que el mes y año sean válidos y que el período no exista
    previamente. Si todo es correcto, inserta el nuevo período en la
    base de datos listo para recibir transacciones.

    Args:
        datos (dict): Cuerpo de la solicitud con:
            - mes (int): Número del mes (1-12).
            - anio (int): Año del período (ej. 2025).
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (400): Si mes o año no fueron proporcionados.
        HTTPException (400): Si el período ya existe en la base de datos.

    Returns:
        dict: {'ok': True, 'mensaje': str} con confirmación del período creado.
    """
    mes  = int(datos.get("mes", 0))
    anio = int(datos.get("anio", 0))

    if not mes or not anio:
        raise HTTPException(status_code=400, detail="Mes y año son requeridos")

    from models.models import Empresa
    empresa_obj = db.query(Empresa).first()

    # Verificar que no exista ya ese período
    existente = db.query(PeriodoContable).filter_by(
        mes=mes, anio=anio
    ).first()
    if existente:
        raise HTTPException(
            status_code=400,
            detail=f"El período {MESES[mes]}-{anio} ya existe"
        )

    # Crear el nuevo período en estado ABIERTO
    nuevo = PeriodoContable(
        id_empresa = empresa_obj.id_empresa,
        mes        = mes,
        anio       = anio,
        estado     = "ABIERTO"
    )
    db.add(nuevo)
    db.commit()
    return {"ok": True, "mensaje": f"Período {MESES[mes]}-{anio} abierto correctamente"}
