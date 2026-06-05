# routers/reportes.py
# Endpoints que generan los reportes contables del período:
# libro diario, libro mayor y estado de resultados.
# Usan las vistas SQL que ya están en ContabilidadGT.
from sqlalchemy import func
from models.models import CuentaContable
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

@router.get("/estado-resultados")
def estado_resultados(request: Request, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    periodo = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    ingresos = []
    gastos = []

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
            .filter(CuentaContable.tipo.in_(["Ingreso", "Gasto"]))
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )

        for fila in filas:
            debe = float(fila.total_debe or 0)
            haber = float(fila.total_haber or 0)

            if fila.tipo == "Ingreso":
                monto = haber - debe
                ingresos.append({"codigo": fila.codigo, "nombre": fila.nombre, "monto": monto})
            elif fila.tipo == "Gasto":
                monto = debe - haber
                gastos.append({"codigo": fila.codigo, "nombre": fila.nombre, "monto": monto})

    total_ingresos = sum(i["monto"] for i in ingresos)
    total_gastos = sum(g["monto"] for g in gastos)
    utilidad = total_ingresos - total_gastos

    return templates.TemplateResponse(
        request=request,
        name="estado_resultados.html",
        context={
            "empresa": empresa,
            "ingresos": ingresos,
            "gastos": gastos,
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "utilidad": utilidad,
            "periodo": f"MAY-{periodo.anio}" if periodo else "—",
            "estado": periodo.estado if periodo else "—",
            "active": "resultados",
        },
    )

@router.get("/libro-mayor")
def libro_mayor(request: Request, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    periodo = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    cuentas_mayor = []

    if periodo:
        # 1. Ejecutamos la consulta agrupando los montos por cada Cuenta Contable
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
            .filter(Transaccion.anulada == False)  # Ignoramos transacciones anuladas
            .group_by(CuentaContable.tipo, CuentaContable.codigo, CuentaContable.nombre)
            .order_by(CuentaContable.codigo)
            .all()
        )

        # 2. Calculamos los saldos netos respetando la naturaleza de las cuentas de Guatemala
        for fila in filas:
            debe = float(fila.total_debe or 0)
            haber = float(fila.total_haber or 0)

            # Cuentas de naturaleza Deudora (Activos, Gastos, Costos)
            if fila.tipo in ["Activo", "Gasto", "Costo", "Egreso"]:
                saldo = debe - haber
            # Cuentas de naturaleza Acreedora (Pasivos, Patrimonio, Ingresos)
            else:
                saldo = haber - debe

            cuentas_mayor.append({
                "codigo": fila.codigo,
                "nombre": fila.nombre,
                "tipo": fila.tipo,
                "debe": debe,
                "haber": haber,
                "saldo": saldo
            })

    return templates.TemplateResponse(
        request=request,
        name="libro_mayor.html",
        context={
            "empresa": empresa,
            "cuentas": cuentas_mayor,
            "periodo": f"MAY-{periodo.anio}" if periodo else "—",
            "estado": periodo.estado if periodo else "—",
            "active": "mayor",
        },
    )