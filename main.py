# main.py
# Punto de entrada de la aplicación.
# Aquí se crea la app FastAPI, se registran todos los routers
# y se configura Jinja2 para las plantillas HTML.

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routers import empresa, inventario, transacciones, reportes, cierre

# ── Crear la aplicación ────────────────────────────────────────
app = FastAPI(
    title="Sistema Contable — Fannys Express",
    description="Software contable para restaurante guatemalteco. "
                "NIT: 327527-J | Totonicapán",
    version="1.0.0",
)

# ── Archivos estáticos (CSS, JS) ───────────────────────────────
# Todo lo que esté en /static/ se sirve directamente al navegador
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Plantillas HTML (Jinja2) ───────────────────────────────────
# Los routers usan esto para renderizar las páginas
templates = Jinja2Templates(directory="templates")

# ── Registrar routers ──────────────────────────────────────────
# Cada router maneja un módulo del sistema:
# /empresa        → datos de Fannys Express
# /inventario     → productos e insumos
# /transacciones  → registro de operaciones del mes
# /reportes       → libro diario, mayor, estado de resultados
# /cierre         → corte mensual automático
app.include_router(empresa.router,       prefix="/empresa",       tags=["Empresa"])
app.include_router(inventario.router,    prefix="/inventario",    tags=["Inventario"])
app.include_router(transacciones.router, prefix="/transacciones", tags=["Transacciones"])
app.include_router(reportes.router,      prefix="/reportes",      tags=["Reportes"])
app.include_router(cierre.router,        prefix="/cierre",        tags=["Cierre"])


# ── Ruta raíz ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "sistema": "Fannys Express — Sistema Contable",
        "version": "1.0.0",
        "docs":    "/docs",
    }
