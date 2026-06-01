# Punto de entrada de la aplicación.
# Aquí se crea la app FastAPI, se registran todos los routers
# y se configura Jinja2 para las plantillas HTML.

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models.models import Transaccion, PartidaDiaria, PeriodoContable, Empresa, InventarioProducto, ActivoFijo, DetallePartida, CuentaContable
from fastapi import FastAPI, Request, Depends


from routers import empresa, inventario, transacciones, reportes, cierre

# ── Crear la aplicación ────────────────────────────────────────
app = FastAPI(
    title="Sistema Contable — Fannys Express",
    description="Software contable para restaurante guatemalteco. "
                "NIT: 327527-J | Totonicapán",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Archivos estáticos (CSS, JS) ───────────────────────────────
# Todo lo que esté en /static/ se sirve directamente al navegador
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Plantillas HTML (Jinja2) ───────────────────────────────────
# Los routers usan esto para renderizar las páginas
templates = Jinja2Templates(directory="templates")

app.include_router(empresa.router,       prefix="/empresa",       tags=["Empresa"])
app.include_router(inventario.router,    prefix="/inventario",    tags=["Inventario"])
app.include_router(transacciones.router, prefix="/transacciones", tags=["Transacciones"])
app.include_router(reportes.router,      prefix="/reportes",      tags=["Reportes"])
app.include_router(cierre.router,        prefix="/cierre",        tags=["Cierre"])


# ── Ruta raíz ─────────────────────────────────────────────────
@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    empresa_obj = db.query(Empresa).first()
    periodo     = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    if not periodo:
        return templates.TemplateResponse(
            request=request, name="dashboard.html",
            context={"periodo": "—", "estado": "—", "total_ventas": 0,
                     "total_gastos": 0, "utilidad": 0, "iva_debito": 0,
                     "iva_credito": 0, "iva_neto": 0, "transacciones": [],
                     "total_asientos": 0, "total_productos": 0,
                     "total_activos": 0, "num_ventas": 0, "num_gastos": 0,
                     "active": "dashboard"}
        )

    txs = db.query(Transaccion).filter_by(
        idperiodo=periodo.idperiodo, anulada=False
    ).order_by(Transaccion.fecha.desc()).limit(6).all()

    todas = db.query(Transaccion).filter_by(
        idperiodo=periodo.idperiodo, anulada=False
    ).all()

    total_ventas  = sum(t.total for t in todas if t.tipo == "VENTA")
    total_gastos  = sum(t.total for t in todas if t.tipo in ("GASTO", "COMPRA", "PAGO"))
    num_ventas    = sum(1 for t in todas if t.tipo == "VENTA")
    num_gastos    = sum(1 for t in todas if t.tipo in ("GASTO", "COMPRA", "PAGO"))

    # IVA
    from sqlalchemy import func
    iva_debito = db.query(func.sum(Transaccion.iva)).filter(
        Transaccion.idperiodo == periodo.idperiodo,
        Transaccion.tipo == "VENTA"
    ).scalar() or 0

    iva_credito = db.query(func.sum(Transaccion.iva)).filter(
        Transaccion.idperiodo == periodo.idperiodo,
        Transaccion.tipo.in_(["COMPRA", "GASTO"])
    ).scalar() or 0

    total_productos = db.query(InventarioProducto).filter_by(
        id_empresa=empresa_obj.id_empresa, activo=True
    ).count()

    total_activos = db.query(ActivoFijo).filter_by(
        id_empresa=empresa_obj.id_empresa, activo=True
    ).count()

    total_asientos = db.query(PartidaDiaria).join(Transaccion).filter(
        Transaccion.idperiodo == periodo.idperiodo
    ).count()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "periodo":          f"MAY-{periodo.anio}",
            "estado":           periodo.estado,
            "total_ventas":     float(total_ventas),
            "total_gastos":     float(total_gastos),
            "utilidad":         float(total_ventas) - float(total_gastos),
            "iva_debito":       float(iva_debito),
            "iva_credito":      float(iva_credito),
            "iva_neto":         float(iva_debito) - float(iva_credito),
            "transacciones":    txs,
            "total_asientos":   total_asientos,
            "total_productos":  total_productos,
            "total_activos":    total_activos,
            "num_ventas":       num_ventas,
            "num_gastos":       num_gastos,
            "active":           "dashboard",
        }
    )
