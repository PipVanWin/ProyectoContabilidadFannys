"""
Controlador HTTP para el módulo de Inventario.

Gestiona productos, insumos y activos fijos de la empresa.
Permite consultar, registrar nuevos ítems manualmente y también
importar inventario masivo desde un archivo Excel (.xlsx),
detectando automáticamente categorías, activos fijos e insumos.
"""

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

# Lista de meses 
MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


@router.get("/")
def inventario(request: Request, db: Session = Depends(get_db)):
    """
    Muestra la página principal del módulo de inventario.

    Carga y separa los ítems activos de la empresa en tres grupos:
    productos (para venta), insumos (materia prima) y activos fijos
    (mobiliario, equipo, etc.). También muestra el total combinado.

    Args:
        request (Request): Objeto de solicitud HTTP.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        TemplateResponse: Renderiza 'inventario.html' con productos,
        insumos, activos fijos y datos del período activo.
    """
    empresa = db.query(Empresa).first()
    periodo = db.query(PeriodoContable).filter_by(estado="ABIERTO").first()

    todos = db.query(InventarioProducto).filter_by(
        id_empresa=empresa.id_empresa, activo=True
    ).all()

    # Separar productos de insumos por categoría
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
    """
    Retorna todos los productos activos de la empresa en formato JSON.

    Endpoint de API consumido por el frontend para poblar selectores
    y listados de productos disponibles.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[dict]: Lista de productos con id, codigo, nombre,
        precio_venta y categoria, ordenados alfabéticamente.
    """
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
    """
    Retorna los productos disponibles para registrar transacciones de VENTA.

    Excluye los insumos (categoría='Insumo') ya que estos no se venden
    directamente sino que se usan como materia prima.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[dict]: Lista de productos vendibles con id, codigo, nombre,
        precio_venta y categoria.
    """
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
    """
    Retorna los insumos disponibles para registrar transacciones de COMPRA.

    Solo retorna ítems con categoría 'Insumo', que son los que se adquieren
    como materia prima. El precio retornado es el costo_unitario (no precio
    de venta) ya que se trata de una compra, no una venta.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[dict]: Lista de insumos con id, codigo, nombre,
        precio_venta (costo unitario) y categoria.
    """
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
    """
    Registra un nuevo ítem en el inventario o activos fijos.

    Según el campo 'tipo' del cuerpo de la solicitud, crea un registro
    en la tabla correspondiente:
      - tipo='activo': crea un ActivoFijo (mobiliario, equipo, etc.)
      - tipo='insumo' o cualquier otro: crea un InventarioProducto.

    Args:
        datos (dict): Cuerpo de la solicitud con los campos:
            - tipo (str): 'activo', 'insumo' o categoría del producto.
            - nombre (str): Nombre del ítem.
            - categoria (str, opcional): Categoría del producto.
            - costo_unitario (float, opcional): Costo de adquisición.
            - precio_venta (float, opcional): Precio de venta al público.
            - cantidad (int, opcional): Existencias iniciales.
            - codigo (str, opcional): Código interno del producto.
            - unidad (str, opcional): Unidad de medida (default: 'unidad').
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        dict: {'ok': True} si el registro fue exitoso.
    """
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
    """
    Importa inventario inicial masivo desde un archivo Excel (.xlsx).

    Lee el archivo fila por fila detectando automáticamente encabezados
    de categoría (texto en mayúsculas) y clasifica cada ítem según
    su categoría en tres grupos:

      - Activos Fijos (TERRENO, EDIFICIOS, MOBILIARIO Y EQUIPO, etc.):
        Se insertan en la tabla ActivoFijo con la cuenta contable correcta.

      - Insumos (INVENTARIO DE MATERIA PRIMA Y MERCADERÍA):
        Se insertan en InventarioProducto con categoría='Insumo'.
        Intenta parsear cantidad y precio del texto de la fila.

      - Cuentas Contables (CAJA, BANCOS, CLIENTES, etc.):
        Se contabilizan pero no se insertan (se manejan como saldos
        de apertura en otro módulo).

    Args:
        archivo (UploadFile): Archivo Excel enviado desde el formulario.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        dict: Número de registros procesados y mensaje de confirmación.
    """
    empresa  = db.query(Empresa).first()
    contenido = await archivo.read()
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True)
    ws = wb.active

    importados = 0
    categoria_actual = None

    # Categorías que se registran como activos fijos
    ACTIVOS_FIJOS = {"TERRENO", "EDIFICIOS", "MOBILIARIO Y EQUIPO",
                     "EQUIPO DE COCINA Y CAFETERÍA", "EQUIPO DE COMPUTACIÓN"}

    # Categorías que son cuentas contables 
    CUENTAS_CONTABLES = {"CAJA", "BANCOS", "CLIENTES",
                         "DOCUMENTOS POR COBRAR", "IVA POR COBRAR"}

    # Categorías que se registran como insumos de inventario
    INSUMOS = {"INVENTARIO DE MATERIA PRIMA Y MERCADERÍA"}

    for fila in ws.iter_rows(values_only=True):
        col0 = str(fila[0]).strip() if fila[0] else ""
        col1 = fila[1]  # valor corriente
        col2 = fila[2]  # valor no corriente

        if not col0 or col0 == "None":
            continue

        # Detectar encabezado de categoría
        es_categoria = (
            col1 is None and col2 is None and
            col0.isupper() and len(col0) > 3 and
            col0 not in ("ACTIVO", "CUENTAS", "SUMATORIA DE CUENTAS DE ACTIVOS")
        )

        if es_categoria:
            categoria_actual = col0
            continue

        # Ignorar filas sin valor numérico
        valor = col1 or col2
        if not valor or categoria_actual is None:
            continue

        
        if col0 in ("CUENTAS", "CUENTAS CORRIENTES", "CUENTAS NO CORRIENTES"):
            continue

        try:
            valor = float(valor)
        except (TypeError, ValueError):
            continue

        # ── Activos Fijos 
        if categoria_actual in ACTIVOS_FIJOS:
            # Asignar cuenta contable según tipo de activo
            if "TERRENO" in categoria_actual:
                idcuenta = 6
            elif "EDIFICIO" in categoria_actual:
                idcuenta = 7
            elif "MOBILIARIO" in categoria_actual:
                idcuenta = 9
            elif "COCINA" in categoria_actual or "CAFETERÍA" in categoria_actual:
                idcuenta = 9
            elif "COMPUTACIÓN" in categoria_actual:
                idcuenta = 10
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

        # ── Insumos de Inventario
        elif categoria_actual in INSUMOS:
            # Parsear cantidad y precio del texto 
            match_cant   = re.match(r'^(\d+)', col0)
            match_precio = re.search(r'Q\.?([\d.]+)', col0)
            cantidad = int(match_cant.group(1))   if match_cant   else 1
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

        # ── Cuentas Contables 
        elif categoria_actual in CUENTAS_CONTABLES:
            importados += 1

    db.commit()
    return {"importados": importados, "mensaje": f"Se procesaron {importados} registros del inventario"}
