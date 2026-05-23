# models/models.py
# Cada clase aquí representa una tabla de ContabilidadGT.
# SQLAlchemy usa estos modelos para leer y escribir datos
# sin necesidad de escribir SQL a mano.

from sqlalchemy import (
    Column, Integer, String, Date, Numeric,
    Boolean, SmallInteger, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base


class Empresa(Base):
    __tablename__ = "Empresa"

    id_empresa   = Column(Integer,     primary_key=True, autoincrement=True)
    nombre       = Column(String(150), nullable=False)
    nit          = Column(String(20),  nullable=False, unique=True)
    direccion    = Column(String(250), nullable=False)
    municipio    = Column(String(100), nullable=False)
    departamento = Column(String(100), nullable=False)
    telefono     = Column(String(20))
    correo       = Column(String(150))

    periodos = relationship("PeriodoContable", back_populates="empresa")
    activos  = relationship("ActivoFijo",      back_populates="empresa")
    productos= relationship("InventarioProducto", back_populates="empresa")


class CuentaContable(Base):
    __tablename__ = "CuentaContable"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    codigo     = Column(String(20), nullable=False, unique=True)
    nombre     = Column(String(150),nullable=False)
    tipo       = Column(String(20), nullable=False)   # Activo|Pasivo|Capital|Ingreso|Gasto
    naturaleza = Column(String(10), nullable=False)   # DEUDORA|ACREEDORA
    grupo      = Column(String(100),nullable=False)
    nivel      = Column(SmallInteger, default=1)
    id_padre   = Column(Integer, ForeignKey("CuentaContable.id"), nullable=True)
    activa     = Column(Boolean, default=True)

    hijos          = relationship("CuentaContable", backref="padre", remote_side=[id])
    saldos         = relationship("SaldoInicial",   back_populates="cuenta")
    activos_fijos  = relationship("ActivoFijo",     back_populates="cuenta")
    detalles       = relationship("DetallePartida", back_populates="cuenta")


class ActivoFijo(Base):
    __tablename__ = "ActivoFijo"

    id                     = Column(Integer,     primary_key=True, autoincrement=True)
    id_empresa             = Column(Integer,     ForeignKey("Empresa.id_empresa"), nullable=False)
    idcuenta               = Column(Integer,     ForeignKey("CuentaContable.id"), nullable=False)
    nombre                 = Column(String(150), nullable=False)
    tipo                   = Column(String(80),  nullable=False)
    valor_compra           = Column(Numeric(15,2), nullable=False)
    depreciacion_acumulada = Column(Numeric(15,2), default=0)
    vida_util_anios        = Column(SmallInteger,  default=5)
    fecha_adquisicion      = Column(Date,          nullable=False)
    activo                 = Column(Boolean,        default=True)

    empresa = relationship("Empresa",        back_populates="activos")
    cuenta  = relationship("CuentaContable", back_populates="activos_fijos")


class InventarioProducto(Base):
    __tablename__ = "InventarioProducto"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    id_empresa     = Column(Integer,     ForeignKey("Empresa.id_empresa"), nullable=False)
    codigo         = Column(String(30))
    nombre         = Column(String(150), nullable=False)
    categoria      = Column(String(100), nullable=False)
    unidad         = Column(String(30),  nullable=False)
    costo_unitario = Column(Numeric(12,2), default=0)
    precio_venta   = Column(Numeric(12,2), default=0)
    cantidad       = Column(Integer,       default=0)
    activo         = Column(Boolean,       default=True)

    empresa  = relationship("Empresa",             back_populates="productos")
    detalles = relationship("DetalleTransaccion",  back_populates="producto")


class PeriodoContable(Base):
    __tablename__ = "PeriodoContable"
    __table_args__ = (UniqueConstraint("id_empresa", "mes", "anio"),)

    idperiodo  = Column(Integer,    primary_key=True, autoincrement=True)
    id_empresa = Column(Integer,    ForeignKey("Empresa.id_empresa"), nullable=False)
    mes        = Column(SmallInteger, nullable=False)
    anio       = Column(SmallInteger, nullable=False)
    estado     = Column(String(10), default="ABIERTO")

    empresa      = relationship("Empresa",      back_populates="periodos")
    transacciones= relationship("Transaccion",  back_populates="periodo")
    saldos       = relationship("SaldoInicial", back_populates="periodo")


class SaldoInicial(Base):
    __tablename__ = "SaldoInicial"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    idperiodo      = Column(Integer,     ForeignKey("PeriodoContable.idperiodo"), nullable=False)
    idcuenta       = Column(Integer,     ForeignKey("CuentaContable.id"),         nullable=False)
    monto          = Column(Numeric(15,2), default=0)
    descripcion    = Column(String(250))
    fecha_apertura = Column(Date,          nullable=False)

    periodo = relationship("PeriodoContable", back_populates="saldos")
    cuenta  = relationship("CuentaContable",  back_populates="saldos")


class Transaccion(Base):
    __tablename__ = "Transaccion"

    idtransaccion = Column(Integer,     primary_key=True, autoincrement=True)
    idperiodo     = Column(Integer,     ForeignKey("PeriodoContable.idperiodo"), nullable=False)
    fecha         = Column(Date,        nullable=False)
    tipo          = Column(String(20),  nullable=False)  # VENTA|COMPRA|GASTO|PAGO|COBRO|APERTURA|CIERRE
    descripcion   = Column(String(300), nullable=False)
    monto_base    = Column(Numeric(15,2), default=0)
    iva           = Column(Numeric(15,2), default=0)
    documento_ref = Column(String(50))
    anulada       = Column(Boolean, default=False)

    periodo  = relationship("PeriodoContable",   back_populates="transacciones")
    detalles = relationship("DetalleTransaccion",back_populates="transaccion")
    partida  = relationship("PartidaDiaria",     back_populates="transaccion", uselist=False)

    @property
    def total(self):
        # total se calcula en Python igual que la columna calculada en SQL Server
        return (self.monto_base or 0) + (self.iva or 0)


class DetalleTransaccion(Base):
    __tablename__ = "DetalleTransaccion"

    iddetalle       = Column(Integer,     primary_key=True, autoincrement=True)
    idtransaccion   = Column(Integer,     ForeignKey("Transaccion.idtransaccion"), nullable=False)
    idproducto      = Column(Integer,     ForeignKey("InventarioProducto.id"),     nullable=True)
    descripcion     = Column(String(200), nullable=False)
    cantidad        = Column(Integer,     default=1)
    precio_unitario = Column(Numeric(12,2), nullable=False)

    transaccion = relationship("Transaccion",         back_populates="detalles")
    producto    = relationship("InventarioProducto",   back_populates="detalles")

    @property
    def subtotal(self):
        return (self.cantidad or 0) * (self.precio_unitario or 0)


class PartidaDiaria(Base):
    __tablename__ = "PartidaDiaria"

    idpartida      = Column(Integer,     primary_key=True, autoincrement=True)
    idtransaccion  = Column(Integer,     ForeignKey("Transaccion.idtransaccion"), nullable=False, unique=True)
    numero_partida = Column(Integer,     nullable=False)
    fecha          = Column(Date,        nullable=False)
    concepto       = Column(String(300), nullable=False)
    tipo_partida   = Column(String(15),  default="NORMAL")  # NORMAL|REGULARIZACION|CIERRE

    transaccion = relationship("Transaccion",   back_populates="partida")
    detalles    = relationship("DetallePartida",back_populates="partida")


class DetallePartida(Base):
    __tablename__ = "DetallePartida"

    id        = Column(Integer,       primary_key=True, autoincrement=True)
    idpartida = Column(Integer,       ForeignKey("PartidaDiaria.idpartida"), nullable=False)
    idcuenta  = Column(Integer,       ForeignKey("CuentaContable.id"),       nullable=False)
    debe      = Column(Numeric(15,2), default=0)
    haber     = Column(Numeric(15,2), default=0)

    partida = relationship("PartidaDiaria",  back_populates="detalles")
    cuenta  = relationship("CuentaContable", back_populates="detalles")
