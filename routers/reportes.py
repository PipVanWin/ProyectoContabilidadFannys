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

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

def _get_periodo(db: Session, idperiodo: int = None) -> PeriodoContable:
    if idperiodo:
        return db.query(PeriodoContable).get(idperiodo)
    return (
        db.query(PeriodoContable).filter_by(estado="ABIERTO").first()
    ) or (
        db.query(PeriodoContable)
        .order_by(PeriodoContable.anio.desc(), PeriodoContable.mes.desc())
        .first()
    )

def _periodo_label(periodo):
    if not periodo:
        return "—"
    return f"{MESES[periodo.mes]}-{periodo.anio}"

@router.get("/libro-diario")
def libro_diario(request: Request, db: Session = Depends(get_db),
                 idperiodo: int = Query(None)):
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
            .filter(Transaccion.tipo != "CIERRE")
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )
        for fila in filas:
            debe  = float(fila.total_debe  or 0)
            haber = float(fila.total_haber or 0)
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
            .filter(Transaccion.tipo != "CIERRE")
            .filter(CuentaContable.tipo.in_(["Ingreso", "Gasto"]))
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )
        for fila in filas:
            debe  = float(fila.total_debe  or 0)
            haber = float(fila.total_haber or 0)
            if fila.tipo == "Ingreso":
                ingresos.append({"codigo": fila.codigo, "nombre": fila.nombre, "monto": haber - debe})
            elif fila.tipo == "Gasto":
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