"""
Controlador HTTP para el módulo de Reportes Contables.
Genera y presenta los tres reportes financieros principales del sistema:
  - Libro Diario: asientos contables cronológicos del período.
  - Libro Mayor: movimientos agrupados por cuenta contable.
  - Estado de Resultados: ingresos, gastos y utilidad/pérdida del período.

Todos los reportes pueden consultarse para el período activo o para
cualquier período histórico pasando el parámetro ?idperiodo=N en la URL.
"""

from sqlalchemy import func
from models.models import CuentaContable
from fastapi import APIRouter, Depends, Request, Query
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models.models import PartidaDiaria, Transaccion, PeriodoContable, Empresa, DetallePartida
from pathlib import Path

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Lista de meses 
MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


def _get_periodo(db: Session, idperiodo: int = None) -> PeriodoContable:
    """
    Obtiene el período contable a usar en los reportes.

    Si se proporciona un ID específico, retorna ese período.
    Si no, busca el período con estado 'ABIERTO'. Como fallback,
    retorna el período más reciente disponible.

    Args:
        db (Session): Sesión de base de datos.
        idperiodo (int, opcional): ID del período a consultar.

    Returns:
        PeriodoContable | None: El período encontrado o None si no existe ninguno.
    """
    if idperiodo:
        return db.query(PeriodoContable).get(idperiodo)
    return (
        db.query(PeriodoContable).filter_by(estado="ABIERTO").first()
    ) or (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .first()
    )


def _periodo_label(periodo) -> str:
    """
    Formatea el período contable como texto legible para la interfaz.

    Args:
        periodo (PeriodoContable | None): Objeto del período contable.

    Returns:
        str: Texto con formato 'Mes-Año' (ej. 'Enero-2025') o '—' si es None.
    """
    if not periodo:
        return "—"
    return f"{MESES[periodo.mes]}-{periodo.anio}"


@router.get("/libro-diario")
def libro_diario(request: Request, db: Session = Depends(get_db),
                 idperiodo: int = Query(None)):
    """
    Muestra el Libro Diario del período contable indicado.

    Carga todas las partidas diarias del período con sus detalles
    (líneas de débito/crédito) y las cuentas contables asociadas,
    ordenadas por número de partida. Excluye transacciones anuladas.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.
        idperiodo (int, opcional): ID del período a consultar.
            Si se omite, usa el período activo.

    Returns:
        TemplateResponse: Renderiza 'libro_diario.html' con todas
        las partidas y sus detalles contables.
    """
    periodo = _get_periodo(db, idperiodo)
    partidas = (
        db.query(PartidaDiaria)
        .join(Transaccion)
        .filter(Transaccion.idperiodo == periodo.idperiodo)
        .options(
            joinedload(PartidaDiaria.detalles).joinedload(DetallePartida.cuenta),
            joinedload(PartidaDiaria.transaccion)
        )
        .order_by(PartidaDiaria.numero_partida)
        .all()
    ) if periodo else []

    return templates.TemplateResponse(
        request=request,
        name="libro_diario.html",
        context={
            "partidas":  partidas,
            "periodo":   _periodo_label(periodo),
            "estado":    periodo.estado if periodo else "—",
            "idperiodo": periodo.idperiodo if periodo else None,
            "active":    "diario",
        }
    )


@router.get("/libro-mayor")
def libro_mayor(request: Request, db: Session = Depends(get_db),
                idperiodo: int = Query(None)):
    """
    Muestra el Libro Mayor del período contable indicado.

    Agrupa todos los movimientos contables por cuenta, calculando
    el total de débitos, créditos y saldo final de cada una.
    El saldo se calcula según la naturaleza de la cuenta:
      - Activo, Gasto, Costo, Egreso: saldo = debe - haber
      - Pasivo, Capital, Ingreso: saldo = haber - debe

    Excluye transacciones anuladas y partidas de cierre contable.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.
        idperiodo (int, opcional): ID del período a consultar.
            Si se omite, usa el período activo.

    Returns:
        TemplateResponse: Renderiza 'libro_mayor.html' con el resumen
        por cuenta (código, nombre, tipo, debe, haber, saldo).
    """
    periodo = _get_periodo(db, idperiodo)
    cuentas_mayor = []

    if periodo:
        filas = (
            db.query(
                CuentaContable.tipo,
                CuentaContable.codigo,
                CuentaContable.nombre,
                func.sum(DetallePartida.debe).label("total_debe"),
                func.sum(DetallePartida.haber).label("total_haber"),
            )
            .join(DetallePartida, DetallePartida.idcuenta == CuentaContable.id)
            .join(PartidaDiaria, PartidaDiaria.idpartida == DetallePartida.idpartida)
            .join(Transaccion, Transaccion.idtransaccion == PartidaDiaria.idtransaccion)
            .filter(Transaccion.idperiodo == periodo.idperiodo)
            .filter(Transaccion.anulada == False)
            .filter(Transaccion.tipo != "CIERRE")  # Excluir partidas de cierre
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )
        for fila in filas:
            debe  = float(fila.total_debe  or 0)
            haber = float(fila.total_haber or 0)
            # Saldo según naturaleza de la cuenta
            saldo = (debe - haber) if fila.tipo in ["Activo","Gasto","Costo","Egreso"] else (haber - debe)
            cuentas_mayor.append({
                "codigo": fila.codigo, "nombre": fila.nombre,
                "tipo": fila.tipo, "debe": debe, "haber": haber, "saldo": saldo
            })

    return templates.TemplateResponse(
        request=request,
        name="libro_mayor.html",
        context={
            "cuentas":   cuentas_mayor,
            "periodo":   _periodo_label(periodo),
            "estado":    periodo.estado if periodo else "—",
            "idperiodo": periodo.idperiodo if periodo else None,
            "active":    "mayor",
        }
    )


@router.get("/estado-resultados")
def estado_resultados(request: Request, db: Session = Depends(get_db),
                      idperiodo: int = Query(None)):
    """
    Muestra el Estado de Resultados del período contable indicado.

    Separa las cuentas contables en dos grupos (Ingreso y Gasto),
    calcula los totales de cada grupo y determina la utilidad o
    pérdida neta del período (utilidad = total ingresos - total gastos).

    Excluye transacciones anuladas y partidas de cierre contable.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.
        idperiodo (int, opcional): ID del período a consultar.
            Si se omite, usa el período activo.

    Returns:
        TemplateResponse: Renderiza 'estado_resultados.html' con:
            - empresa: datos fiscales de la empresa.
            - ingresos: lista de cuentas de ingreso con montos.
            - gastos: lista de cuentas de gasto con montos.
            - total_ingresos, total_gastos, utilidad: totales calculados.
    """
    empresa = db.query(Empresa).first()
    periodo = _get_periodo(db, idperiodo)
    ingresos, gastos = [], []

    if periodo:
        filas = (
            db.query(
                CuentaContable.tipo,
                CuentaContable.codigo,
                CuentaContable.nombre,
                func.sum(DetallePartida.debe).label("total_debe"),
                func.sum(DetallePartida.haber).label("total_haber"),
            )
            .join(DetallePartida, DetallePartida.idcuenta == CuentaContable.id)
            .join(PartidaDiaria, PartidaDiaria.idpartida == DetallePartida.idpartida)
            .join(Transaccion, Transaccion.idtransaccion == PartidaDiaria.idtransaccion)
            .filter(Transaccion.idperiodo == periodo.idperiodo)
            .filter(Transaccion.anulada == False)
            .filter(Transaccion.tipo != "CIERRE")  # Excluir partidas de cierre
            .filter(CuentaContable.tipo.in_(["Ingreso", "Gasto"]))
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )
        for fila in filas:
            debe  = float(fila.total_debe  or 0)
            haber = float(fila.total_haber or 0)
            if fila.tipo == "Ingreso":
                # Ingresos tienen naturaleza acreedora: saldo = haber - debe
                ingresos.append({"codigo": fila.codigo, "nombre": fila.nombre, "monto": haber - debe})
            elif fila.tipo == "Gasto":
                # Gastos tienen naturaleza deudora: saldo = debe - haber
                gastos.append({"codigo": fila.codigo, "nombre": fila.nombre, "monto": debe - haber})

    total_ingresos = sum(i["monto"] for i in ingresos)
    total_gastos   = sum(g["monto"] for g in gastos)

    return templates.TemplateResponse(
        request=request,
        name="estado_resultados.html",
        context={
            "empresa":         empresa,
            "ingresos":        ingresos,
            "gastos":          gastos,
            "total_ingresos":  total_ingresos,
            "total_gastos":    total_gastos,
            "utilidad":        total_ingresos - total_gastos,
            "periodo":         _periodo_label(periodo),
            "estado":          periodo.estado if periodo else "—",
            "idperiodo":       periodo.idperiodo if periodo else None,
            "active":          "resultados",
        }
    )
