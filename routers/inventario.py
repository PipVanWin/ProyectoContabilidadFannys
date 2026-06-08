from pathlib import Path
from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models.models import InventarioProducto, ActivoFijo, Empresa, PeriodoContable
import openpyxl
import io
import re

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

@router.get("/")
def inventario(request: Request, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    periodo = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    todos = db.query(InventarioProducto).filter_by(
        id_empresa=empresa.id_empresa, activo=True
    ).all()

    productos = [p for p in todos if p.categoria != "Insumo"]
    insumos   = [p for p in todos if p.categoria == "Insumo"]
    activos   = db.query(ActivoFijo).filter_by(
        id_empresa=empresa.id_empresa, activo=True
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="inventario.html",
        context={
            "productos":   productos,
            "insumos":     insumos,
            "activos":     activos,
            "total_items": len(todos) + len(activos),
            "periodo": f"{MESES[periodo.mes]}-{periodo.anio}" if periodo else "—",
            "estado":      periodo.estado if periodo else "—",
            "active":      "inventario",
        }
    )

@router.get("/productos")
def listar_productos(db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    productos = db.query(InventarioProducto).filter_by(
        id_empresa=empresa.id_empresa, activo=True
    ).order_by(InventarioProducto.nombre).all()
    return [
        {"id": p.id, "codigo": p.codigo, "nombre": p.nombre,
         "precio_venta": float(p.precio_venta), "categoria": p.categoria}
        for p in productos
    ]

@router.get("/productos/venta")
def productos_venta(db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    productos = db.query(InventarioProducto).filter(
        InventarioProducto.id_empresa == empresa.id_empresa,
        InventarioProducto.activo == True,
        InventarioProducto.categoria != "Insumo"
    ).order_by(InventarioProducto.nombre).all()
    return [
        {"id": p.id, "codigo": p.codigo, "nombre": p.nombre,
         "precio_venta": float(p.precio_venta), "categoria": p.categoria}
        for p in productos
    ]

@router.get("/productos/compra")
def productos_compra(db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()
    productos = db.query(InventarioProducto).filter(
        InventarioProducto.id_empresa == empresa.id_empresa,
        InventarioProducto.activo == True,
        InventarioProducto.categoria == "Insumo"
    ).order_by(InventarioProducto.nombre).all()
    return [
        {"id": p.id, "codigo": p.codigo, "nombre": p.nombre,
         "precio_venta": float(p.costo_unitario), "categoria": p.categoria}
        for p in productos
    ]

@router.post("/nuevo")
def nuevo_item(datos: dict, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).first()

    if datos.get("tipo") == "activo":
        activo = ActivoFijo(
            id_empresa        = empresa.id_empresa,
            idcuenta          = 9,
            nombre            = datos["nombre"],
            tipo              = datos.get("categoria", "General"),
            valor_compra      = datos.get("costo_unitario", 0),
            fecha_adquisicion = "2025-05-01",
        )
        db.add(activo)
    else:
        item = InventarioProducto(
            id_empresa     = empresa.id_empresa,
            codigo         = datos.get("codigo"),
            nombre         = datos["nombre"],
            categoria      = datos.get("categoria", "Insumo" if datos.get("tipo") == "insumo" else "General"),
            unidad         = datos.get("unidad", "unidad"),
            costo_unitario = datos.get("costo_unitario", 0),
            precio_venta   = datos.get("precio_venta", 0),
            cantidad       = datos.get("cantidad", 0),
        )
        db.add(item)

    db.commit()
    return {"ok": True}

@router.post("/importar-excel")
async def importar_excel(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    empresa  = db.query(Empresa).first()
    contenido = await archivo.read()
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True)
    ws = wb.active

    importados = 0
    categoria_actual = None

    # Categorías que son activos fijos
    ACTIVOS_FIJOS = {"TERRENO", "EDIFICIOS", "MOBILIARIO Y EQUIPO",
                     "EQUIPO DE COCINA Y CAFETERÍA", "EQUIPO DE COMPUTACIÓN"}

    # Categorías que son activo corriente (cuentas contables, no inventario físico)
    CUENTAS_CONTABLES = {"CAJA", "BANCOS", "CLIENTES",
                         "DOCUMENTOS POR COBRAR", "IVA POR COBRAR"}

    # Categorías de inventario de insumos
    INSUMOS = {"INVENTARIO DE MATERIA PRIMA Y MERCADERÍA"}

    for fila in ws.iter_rows(values_only=True):
        col0 = str(fila[0]).strip() if fila[0] else ""
        col1 = fila[1]  # valor corriente
        col2 = fila[2]  # valor no corriente

        if not col0 or col0 == "None":
            continue

        # Detectar si es un encabezado de categoría
        es_categoria = (
            col1 is None and col2 is None and
            col0.isupper() and len(col0) > 3 and
            col0 not in ("ACTIVO", "CUENTAS", "SUMATORIA DE CUENTAS DE ACTIVOS")
        )

        if es_categoria:
            categoria_actual = col0
            continue

        # Ignorar filas que no tienen valor
        valor = col1 or col2
        if not valor or categoria_actual is None:
            continue

        # Ignorar filas de encabezado de columnas
        if col0 in ("CUENTAS", "CUENTAS CORRIENTES", "CUENTAS NO CORRIENTES"):
            continue

        try:
            valor = float(valor)
        except (TypeError, ValueError):
            continue

        # Activos fijos → tabla ActivoFijo
        if categoria_actual in ACTIVOS_FIJOS:
            # Buscar cuenta contable correcta
            if "TERRENO" in categoria_actual:
                idcuenta = 6   # Terrenos
            elif "EDIFICIO" in categoria_actual:
                idcuenta = 7   # Edificios
            elif "MOBILIARIO" in categoria_actual:
                idcuenta = 9   # Mobiliario
            elif "COCINA" in categoria_actual or "CAFETERÍA" in categoria_actual:
                idcuenta = 9
            elif "COMPUTACIÓN" in categoria_actual:
                idcuenta = 10  # Equipo de cómputo
            else:
                idcuenta = 9

            activo = ActivoFijo(
                id_empresa        = empresa.id_empresa,
                idcuenta          = idcuenta,
                nombre            = col0,
                tipo              = categoria_actual.title(),
                valor_compra      = valor,
                fecha_adquisicion = "2025-05-01",
            )
            db.add(activo)
            importados += 1

        # Insumos → tabla InventarioProducto
        elif categoria_actual in INSUMOS:
            # Parsear cantidad y precio del texto — "20 lb de café a Q.70.00"
            import re
            match_cant = re.match(r'^(\d+)', col0)
            match_precio = re.search(r'Q\.?([\d.]+)', col0)
            cantidad = int(match_cant.group(1)) if match_cant else 1
            costo    = float(match_precio.group(1)) if match_precio else valor

            item = InventarioProducto(
                id_empresa     = empresa.id_empresa,
                nombre         = col0,
                categoria      = "Insumo",
                unidad         = "unidad",
                costo_unitario = costo,
                precio_venta   = 0,
                cantidad       = cantidad,
            )
            db.add(item)
            importados += 1

        # Cuentas contables (Caja, Bancos, etc.) → SaldoInicial
        elif categoria_actual in CUENTAS_CONTABLES:
            # Por ahora solo contamos, los saldos iniciales
            # se manejan en la pantalla de saldos de apertura
            importados += 1

    db.commit()
    return {"importados": importados, "mensaje": f"Se procesaron {importados} registros del inventario"}