"""
Controlador HTTP para la gestión de la empresa y períodos contables.

Expone endpoints para consultar los datos fiscales de Fannys Express,
listar y crear períodos contables, y consultar el catálogo completo
de cuentas contables del sistema.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.models import Empresa, PeriodoContable

router = APIRouter()


@router.get("/")
def obtener_empresa(db: Session = Depends(get_db)):
    """
    Retorna los datos fiscales de la empresa (Fannys Express).

    Consulta el único registro de empresa registrado en el sistema.
    Incluye nombre comercial, NIT, dirección, municipio y departamento.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (404): Si no existe ninguna empresa registrada.

    Returns:
        Empresa: Objeto ORM con todos los datos fiscales de la empresa.
    """
    empresa = db.query(Empresa).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa


@router.get("/periodos")
def listar_periodos(db: Session = Depends(get_db)):
    """
    Lista todos los períodos contables registrados en el sistema.

    Retorna todos los períodos sin filtrar, incluyendo tanto los
    períodos abiertos como los cerrados.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[PeriodoContable]: Lista completa de períodos contables.
    """
    return db.query(PeriodoContable).all()


@router.get("/cuentas")
def listar_cuentas(db: Session = Depends(get_db)):
    """
    Retorna el catálogo completo de cuentas contables del sistema.

    Lista todas las cuentas del plan contable ordenadas por código,
    incluyendo su tipo (Activo, Pasivo, Capital, Ingreso, Gasto, etc.)
    y nivel jerárquico dentro del plan de cuentas.

    Args:
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        list[dict]: Lista de cuentas con id, codigo, nombre, tipo y nivel.
    """
    from models.models import CuentaContable
    cuentas = db.query(CuentaContable).order_by(CuentaContable.codigo).all()
    return [
        {"id": c.id, "codigo": c.codigo, "nombre": c.nombre,
         "tipo": c.tipo, "nivel": c.nivel}
        for c in cuentas
    ]


@router.post("/periodos")
def crear_periodo(mes: int, anio: int, db: Session = Depends(get_db)):
    """
    Abre un nuevo período contable para el mes y año indicados.

    Verifica que no exista ya un período para esa combinación
    mes/año de la empresa antes de crearlo. El nuevo período
    queda en estado 'ABIERTO' listo para recibir transacciones.

    Args:
        mes (int): Número del mes del período (1-12).
        anio (int): Año del período (ej. 2025).
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Raises:
        HTTPException (400): Si ya existe un período para ese mes y año.

    Returns:
        PeriodoContable: El nuevo período contable creado y confirmado.
    """
    empresa = db.query(Empresa).first()
    existente = db.query(PeriodoContable).filter_by(
        id_empresa=empresa.id_empresa, mes=mes, anio=anio
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="El período ya existe")

    periodo = PeriodoContable(id_empresa=empresa.id_empresa, mes=mes, anio=anio)
    db.add(periodo)
    db.commit()
    db.refresh(periodo)
    return periodo
