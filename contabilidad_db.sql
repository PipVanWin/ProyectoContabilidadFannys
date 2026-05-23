USE master;
GO

IF EXISTS (SELECT name FROM sys.databases WHERE name = N'ContabilidadGT')
    DROP DATABASE ContabilidadGT;
GO

CREATE DATABASE ContabilidadGT
    COLLATE Modern_Spanish_CI_AS;
GO

USE ContabilidadGT;
GO

-- ============================================================
-- TABLAS (en orden de dependencia, sin referencias circulares)
-- ============================================================

-- ------------------------------------------------------------
-- 1. EMPRESA
-- ------------------------------------------------------------
CREATE TABLE Empresa (
    id_empresa   INT          NOT NULL IDENTITY(1,1),
    nombre       VARCHAR(150) NOT NULL,
    nit          VARCHAR(20)  NOT NULL,
    direccion    VARCHAR(250) NOT NULL,
    municipio    VARCHAR(100) NOT NULL,
    departamento VARCHAR(100) NOT NULL,
    telefono     VARCHAR(20)      NULL,
    correo       VARCHAR(150)     NULL,

    CONSTRAINT PK_Empresa     PRIMARY KEY (id_empresa),
    CONSTRAINT UQ_Empresa_NIT UNIQUE      (nit)
);
GO

-- ------------------------------------------------------------
-- 2. CUENTA CONTABLE
--    Nodo central: conecta DetallePartida, ActivoFijo y SaldoInicial
-- ------------------------------------------------------------
CREATE TABLE CuentaContable (
    id         INT          NOT NULL IDENTITY(1,1),
    codigo     VARCHAR(20)  NOT NULL,
    nombre     VARCHAR(150) NOT NULL,
    tipo       VARCHAR(20)  NOT NULL,   -- Activo | Pasivo | Capital | Ingreso | Gasto
    naturaleza VARCHAR(10)  NOT NULL,   -- DEUDORA | ACREEDORA
    grupo      VARCHAR(100) NOT NULL,
    nivel      TINYINT      NOT NULL DEFAULT 1,
    id_padre   INT              NULL,
    activa     BIT          NOT NULL DEFAULT 1,

    CONSTRAINT PK_CuentaContable     PRIMARY KEY (id),
    CONSTRAINT UQ_CuentaContable_Cod UNIQUE      (codigo),
    CONSTRAINT FK_Cuenta_Padre       FOREIGN KEY (id_padre)
        REFERENCES CuentaContable(id),
    CONSTRAINT CK_Cuenta_Tipo        CHECK (tipo IN
        ('Activo','Pasivo','Capital','Ingreso','Gasto')),
    CONSTRAINT CK_Cuenta_Naturaleza  CHECK (naturaleza IN ('DEUDORA','ACREEDORA'))
);
GO

-- ------------------------------------------------------------
-- 3. ACTIVO FIJO
--    CuentaContable clasifica a ActivoFijo  (idcuenta FK)
-- ------------------------------------------------------------
CREATE TABLE ActivoFijo (
    id                     INT           NOT NULL IDENTITY(1,1),
    id_empresa             INT           NOT NULL,
    idcuenta               INT           NOT NULL,   -- FK -> CuentaContable
    nombre                 VARCHAR(150)  NOT NULL,
    tipo                   VARCHAR(80)   NOT NULL,
    valor_compra           DECIMAL(15,2) NOT NULL,
    depreciacion_acumulada DECIMAL(15,2) NOT NULL DEFAULT 0,
    valor_en_libros        AS (valor_compra - depreciacion_acumulada),
    vida_util_anios        TINYINT       NOT NULL DEFAULT 5,
    fecha_adquisicion      DATE          NOT NULL,
    activo                 BIT           NOT NULL DEFAULT 1,

    CONSTRAINT PK_ActivoFijo         PRIMARY KEY (id),
    CONSTRAINT FK_ActivoFijo_Empresa FOREIGN KEY (id_empresa)
        REFERENCES Empresa(id_empresa),
    CONSTRAINT FK_ActivoFijo_Cuenta  FOREIGN KEY (idcuenta)
        REFERENCES CuentaContable(id),
    CONSTRAINT CK_ActivoFijo_Valor   CHECK (valor_compra           >= 0),
    CONSTRAINT CK_ActivoFijo_Dep     CHECK (depreciacion_acumulada >= 0)
);
GO

-- ------------------------------------------------------------
-- 4. INVENTARIO PRODUCTO
--    DetalleTransaccion -> InventarioProducto  (idproducto FK)
-- ------------------------------------------------------------
CREATE TABLE InventarioProducto (
    id             INT           NOT NULL IDENTITY(1,1),
    id_empresa     INT           NOT NULL,
    codigo         VARCHAR(30)       NULL,
    nombre         VARCHAR(150)  NOT NULL,
    categoria      VARCHAR(100)  NOT NULL,
    unidad         VARCHAR(30)   NOT NULL,
    costo_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
    precio_venta   DECIMAL(12,2) NOT NULL DEFAULT 0,
    cantidad       INT           NOT NULL DEFAULT 0,
    valor_total    AS (cantidad * costo_unitario),
    activo         BIT           NOT NULL DEFAULT 1,

    CONSTRAINT PK_InventarioProducto  PRIMARY KEY (id),
    CONSTRAINT FK_Inventario_Empresa  FOREIGN KEY (id_empresa)
        REFERENCES Empresa(id_empresa),
    CONSTRAINT CK_Inventario_Costo    CHECK (costo_unitario >= 0),
    CONSTRAINT CK_Inventario_Precio   CHECK (precio_venta   >= 0),
    CONSTRAINT CK_Inventario_Cantidad CHECK (cantidad       >= 0)
);
GO

-- ------------------------------------------------------------
-- 5. PERIODO CONTABLE
--    Raiz del ciclo contable: contiene Transacciones
-- ------------------------------------------------------------
CREATE TABLE PeriodoContable (
    idperiodo  INT         NOT NULL IDENTITY(1,1),
    id_empresa INT         NOT NULL,
    mes        TINYINT     NOT NULL,
    anio       SMALLINT    NOT NULL,
    estado     VARCHAR(10) NOT NULL DEFAULT 'ABIERTO',

    CONSTRAINT PK_PeriodoContable  PRIMARY KEY (idperiodo),
    CONSTRAINT FK_Periodo_Empresa  FOREIGN KEY (id_empresa)
        REFERENCES Empresa(id_empresa),
    CONSTRAINT UQ_Periodo_MesAnio  UNIQUE (id_empresa, mes, anio),
    CONSTRAINT CK_Periodo_Mes      CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT CK_Periodo_Anio     CHECK (anio BETWEEN 2000 AND 2100),
    CONSTRAINT CK_Periodo_Estado   CHECK (estado IN ('ABIERTO','CERRADO'))
);
GO

-- ------------------------------------------------------------
-- 6. SALDO INICIAL
--    CuentaContable se conecta con SaldoInicial  (idcuenta FK)
--    Tambien referencia PeriodoContable
-- ------------------------------------------------------------
CREATE TABLE SaldoInicial (
    id             INT           NOT NULL IDENTITY(1,1),
    idperiodo      INT           NOT NULL,   -- FK -> PeriodoContable
    idcuenta       INT           NOT NULL,   -- FK -> CuentaContable
    monto          DECIMAL(15,2) NOT NULL DEFAULT 0,
    descripcion    VARCHAR(250)      NULL,
    fecha_apertura DATE          NOT NULL DEFAULT GETDATE(),

    CONSTRAINT PK_SaldoInicial          PRIMARY KEY (id),
    CONSTRAINT FK_SaldoI_Periodo        FOREIGN KEY (idperiodo)
        REFERENCES PeriodoContable(idperiodo),
    CONSTRAINT FK_SaldoI_Cuenta         FOREIGN KEY (idcuenta)
        REFERENCES CuentaContable(id),
    CONSTRAINT UQ_SaldoI_CuentaPeriodo  UNIQUE (idperiodo, idcuenta)
);
GO

-- ------------------------------------------------------------
-- 7. TRANSACCION
--    PeriodoContable contiene Transacciones  (idperiodo FK)
-- ------------------------------------------------------------
CREATE TABLE Transaccion (
    idtransaccion INT           NOT NULL IDENTITY(1,1),
    idperiodo     INT           NOT NULL,   -- FK -> PeriodoContable
    fecha         DATE          NOT NULL,
    tipo          VARCHAR(20)   NOT NULL,   -- VENTA|COMPRA|GASTO|PAGO|COBRO|APERTURA|CIERRE
    descripcion   VARCHAR(300)  NOT NULL,
    monto_base    DECIMAL(15,2) NOT NULL DEFAULT 0,
    iva           DECIMAL(15,2) NOT NULL DEFAULT 0,
    total         AS (monto_base + iva),
    documento_ref VARCHAR(50)       NULL,
    anulada       BIT           NOT NULL DEFAULT 0,

    CONSTRAINT PK_Transaccion         PRIMARY KEY (idtransaccion),
    CONSTRAINT FK_Transaccion_Periodo FOREIGN KEY (idperiodo)
        REFERENCES PeriodoContable(idperiodo),
    CONSTRAINT CK_Transaccion_Tipo    CHECK (tipo IN
        ('VENTA','COMPRA','GASTO','PAGO','COBRO','APERTURA','CIERRE','OTRO')),
    CONSTRAINT CK_Transaccion_Base    CHECK (monto_base >= 0),
    CONSTRAINT CK_Transaccion_IVA     CHECK (iva        >= 0)
);
GO

-- ------------------------------------------------------------
-- 8. DETALLE TRANSACCION
--    Transaccion incluye DetalleTransaccion  (idtransaccion FK)
--    DetalleTransaccion usa InventarioProducto  (idproducto FK)
-- ------------------------------------------------------------
CREATE TABLE DetalleTransaccion (
    iddetalle       INT           NOT NULL IDENTITY(1,1),
    idtransaccion   INT           NOT NULL,   -- FK -> Transaccion
    idproducto      INT               NULL,   -- FK -> InventarioProducto (NULL si es gasto sin producto)
    descripcion     VARCHAR(200)  NOT NULL,
    cantidad        INT           NOT NULL DEFAULT 1,
    precio_unitario DECIMAL(12,2) NOT NULL,
    subtotal        AS (cantidad * precio_unitario),

    CONSTRAINT PK_DetalleTransaccion    PRIMARY KEY (iddetalle),
    CONSTRAINT FK_DetalleTx_Transaccion FOREIGN KEY (idtransaccion)
        REFERENCES Transaccion(idtransaccion),
    CONSTRAINT FK_DetalleTx_Producto    FOREIGN KEY (idproducto)
        REFERENCES InventarioProducto(id),
    CONSTRAINT CK_DetalleTx_Cantidad    CHECK (cantidad        >  0),
    CONSTRAINT CK_DetalleTx_Precio      CHECK (precio_unitario >= 0)
);
GO

-- ------------------------------------------------------------
-- 9. PARTIDA DIARIA  (Libro Diario)
--    Transaccion genera PartidaDiaria  (idtransaccion FK, relacion 1:1)
-- ------------------------------------------------------------
CREATE TABLE PartidaDiaria (
    idpartida      INT          NOT NULL IDENTITY(1,1),
    idtransaccion  INT          NOT NULL,   -- FK -> Transaccion  (1:1)
    numero_partida INT          NOT NULL,
    fecha          DATE         NOT NULL,
    concepto       VARCHAR(300) NOT NULL,
    tipo_partida   VARCHAR(15)  NOT NULL DEFAULT 'NORMAL',  -- NORMAL|REGULARIZACION|CIERRE

    CONSTRAINT PK_PartidaDiaria          PRIMARY KEY (idpartida),
    CONSTRAINT FK_Partida_Transaccion    FOREIGN KEY (idtransaccion)
        REFERENCES Transaccion(idtransaccion),
    CONSTRAINT UQ_Partida_Transaccion    UNIQUE (idtransaccion),   -- garantiza 1:1
    CONSTRAINT CK_Partida_Tipo           CHECK (tipo_partida IN
        ('NORMAL','REGULARIZACION','CIERRE'))
);
GO

-- ------------------------------------------------------------
-- 10. DETALLE PARTIDA  (lineas debe/haber del Libro Diario)
--     PartidaDiaria desglosa DetallePartida  (idpartida FK)
--     DetallePartida afecta CuentaContable   (idcuenta  FK)
-- ------------------------------------------------------------
CREATE TABLE DetallePartida (
    id        INT           NOT NULL IDENTITY(1,1),
    idpartida INT           NOT NULL,   -- FK -> PartidaDiaria
    idcuenta  INT           NOT NULL,   -- FK -> CuentaContable
    debe      DECIMAL(15,2) NOT NULL DEFAULT 0,
    haber     DECIMAL(15,2) NOT NULL DEFAULT 0,

    CONSTRAINT PK_DetallePartida      PRIMARY KEY (id),
    CONSTRAINT FK_DetallePart_Partida FOREIGN KEY (idpartida)
        REFERENCES PartidaDiaria(idpartida),
    CONSTRAINT FK_DetallePart_Cuenta  FOREIGN KEY (idcuenta)
        REFERENCES CuentaContable(id),
    CONSTRAINT CK_DetallePart_Debe    CHECK (debe  >= 0),
    CONSTRAINT CK_DetallePart_Haber   CHECK (haber >= 0),
    CONSTRAINT CK_DetallePart_NoAmbos CHECK (NOT (debe > 0 AND haber > 0))
);
GO

-- ============================================================
-- INDICES
-- ============================================================
CREATE INDEX IX_Transaccion_Periodo   ON Transaccion        (idperiodo);
CREATE INDEX IX_DetalleTx_Transaccion ON DetalleTransaccion (idtransaccion);
CREATE INDEX IX_DetalleTx_Producto    ON DetalleTransaccion (idproducto);
CREATE INDEX IX_Partida_Transaccion   ON PartidaDiaria      (idtransaccion);
CREATE INDEX IX_DetalleP_Partida      ON DetallePartida     (idpartida);
CREATE INDEX IX_DetalleP_Cuenta       ON DetallePartida     (idcuenta);
CREATE INDEX IX_SaldoI_Periodo        ON SaldoInicial       (idperiodo);
CREATE INDEX IX_SaldoI_Cuenta         ON SaldoInicial       (idcuenta);
CREATE INDEX IX_ActivoFijo_Cuenta     ON ActivoFijo         (idcuenta);
GO

-- ============================================================
-- VISTAS
-- ============================================================

-- Libro Diario completo
CREATE VIEW vw_LibroDiario AS
SELECT
    pd.numero_partida,
    pd.fecha,
    pd.concepto,
    pd.tipo_partida,
    t.tipo                  AS tipo_transaccion,
    t.documento_ref,
    cc.codigo               AS cod_cuenta,
    cc.nombre               AS cuenta,
    cc.tipo                 AS tipo_cuenta,
    dp.debe,
    dp.haber,
    pc.mes,
    pc.anio,
    e.nombre                AS empresa
FROM PartidaDiaria   pd
JOIN Transaccion     t   ON t.idtransaccion  = pd.idtransaccion
JOIN PeriodoContable pc  ON pc.idperiodo     = t.idperiodo
JOIN Empresa         e   ON e.id_empresa     = pc.id_empresa
JOIN DetallePartida  dp  ON dp.idpartida     = pd.idpartida
JOIN CuentaContable  cc  ON cc.id            = dp.idcuenta;
GO

-- Libro Mayor (saldos por cuenta)
CREATE VIEW vw_LibroMayor AS
SELECT
    pc.idperiodo,
    pc.mes,
    pc.anio,
    e.nombre                     AS empresa,
    cc.codigo                    AS cod_cuenta,
    cc.nombre                    AS cuenta,
    cc.tipo,
    cc.naturaleza,
    SUM(dp.debe)                 AS total_debe,
    SUM(dp.haber)                AS total_haber,
    SUM(dp.debe) - SUM(dp.haber) AS saldo
FROM DetallePartida  dp
JOIN PartidaDiaria   pd  ON pd.idpartida    = dp.idpartida
JOIN Transaccion     t   ON t.idtransaccion = pd.idtransaccion
JOIN PeriodoContable pc  ON pc.idperiodo    = t.idperiodo
JOIN Empresa         e   ON e.id_empresa    = pc.id_empresa
JOIN CuentaContable  cc  ON cc.id           = dp.idcuenta
GROUP BY
    pc.idperiodo, pc.mes, pc.anio, e.nombre,
    cc.codigo, cc.nombre, cc.tipo, cc.naturaleza;
GO

-- Estado de Resultados
CREATE VIEW vw_EstadoResultados AS
SELECT
    pc.idperiodo,
    pc.mes,
    pc.anio,
    e.nombre                     AS empresa,
    cc.tipo,
    cc.codigo                    AS cod_cuenta,
    cc.nombre                    AS cuenta,
    SUM(dp.debe)                 AS total_debe,
    SUM(dp.haber)                AS total_haber,
    CASE
        WHEN cc.tipo = 'Ingreso' THEN SUM(dp.haber) - SUM(dp.debe)
        WHEN cc.tipo = 'Gasto'   THEN SUM(dp.debe)  - SUM(dp.haber)
        ELSE 0
    END                          AS saldo_neto
FROM DetallePartida  dp
JOIN PartidaDiaria   pd  ON pd.idpartida    = dp.idpartida
JOIN Transaccion     t   ON t.idtransaccion = pd.idtransaccion
JOIN PeriodoContable pc  ON pc.idperiodo    = t.idperiodo
JOIN Empresa         e   ON e.id_empresa    = pc.id_empresa
JOIN CuentaContable  cc  ON cc.id           = dp.idcuenta
WHERE cc.tipo IN ('Ingreso','Gasto')
GROUP BY
    pc.idperiodo, pc.mes, pc.anio, e.nombre,
    cc.tipo, cc.codigo, cc.nombre;
GO

-- Regularizacion IVA
CREATE VIEW vw_RegularizacionIVA AS
SELECT
    pc.idperiodo,
    pc.mes,
    pc.anio,
    e.nombre                                        AS empresa,
    SUM(CASE WHEN t.tipo = 'VENTA'
             THEN t.iva ELSE 0 END)                 AS iva_debito_fiscal,
    SUM(CASE WHEN t.tipo IN ('COMPRA','GASTO')
             THEN t.iva ELSE 0 END)                 AS iva_credito_fiscal,
    SUM(CASE WHEN t.tipo = 'VENTA'
             THEN t.iva ELSE 0 END)
  - SUM(CASE WHEN t.tipo IN ('COMPRA','GASTO')
             THEN t.iva ELSE 0 END)                 AS iva_por_pagar
FROM Transaccion     t
JOIN PeriodoContable pc ON pc.idperiodo = t.idperiodo
JOIN Empresa         e  ON e.id_empresa = pc.id_empresa
WHERE t.anulada = 0
GROUP BY pc.idperiodo, pc.mes, pc.anio, e.nombre;
GO

-- ============================================================
-- CATALOGO DE CUENTAS BASE (Plan guatemalteco con IVA)
-- ============================================================
INSERT INTO CuentaContable (codigo, nombre, tipo, naturaleza, grupo, nivel) VALUES
('1',     'ACTIVO',                         'Activo',  'DEUDORA',   'Activo',              1),
('1.1',   'ACTIVO CORRIENTE',               'Activo',  'DEUDORA',   'Activo Corriente',    2),
('1.1.1', 'Caja',                           'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.1.2', 'Banco',                          'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.1.3', 'Cuentas por Cobrar',             'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.1.4', 'Inventario de Mercancias',       'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.1.5', 'IVA Credito Fiscal',             'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.1.6', 'Papeleria y Utiles',             'Activo',  'DEUDORA',   'Activo Corriente',    3),
('1.2',   'ACTIVO NO CORRIENTE',            'Activo',  'DEUDORA',   'Activo No Corriente', 2),
('1.2.1', 'Mobiliario y Equipo',            'Activo',  'DEUDORA',   'Activo No Corriente', 3),
('1.2.2', 'Vehiculos',                      'Activo',  'DEUDORA',   'Activo No Corriente', 3),
('1.2.3', 'Dep. Acum. Mob. y Equipo',       'Activo',  'ACREEDORA', 'Activo No Corriente', 3),
('2',     'PASIVO',                         'Pasivo',  'ACREEDORA', 'Pasivo',              1),
('2.1',   'PASIVO CORRIENTE',               'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    2),
('2.1.1', 'Cuentas por Pagar',              'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    3),
('2.1.2', 'IVA Debito Fiscal',              'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    3),
('2.1.3', 'IVA por Pagar',                  'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    3),
('2.1.4', 'Sueldos por Pagar',              'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    3),
('2.1.5', 'IGSS por Pagar',                 'Pasivo',  'ACREEDORA', 'Pasivo Corriente',    3),
('3',     'CAPITAL',                        'Capital', 'ACREEDORA', 'Capital',             1),
('3.1',   'Capital Contable',               'Capital', 'ACREEDORA', 'Capital',             2),
('3.1.1', 'Capital Inicial',                'Capital', 'ACREEDORA', 'Capital',             3),
('3.1.2', 'Utilidad del Ejercicio',         'Capital', 'ACREEDORA', 'Capital',             3),
('3.1.3', 'Perdida del Ejercicio',          'Capital', 'DEUDORA',   'Capital',             3),
('4',     'INGRESOS',                       'Ingreso', 'ACREEDORA', 'Ingresos',            1),
('4.1',   'Ventas',                         'Ingreso', 'ACREEDORA', 'Ingresos',            2),
('4.1.1', 'Ventas de Mercancias',           'Ingreso', 'ACREEDORA', 'Ingresos',            3),
('4.1.2', 'Descuentos sobre Ventas',        'Ingreso', 'DEUDORA',   'Ingresos',            3),
('4.2',   'Otros Ingresos',                 'Ingreso', 'ACREEDORA', 'Ingresos',            2),
('5',     'GASTOS',                         'Gasto',   'DEUDORA',   'Gastos',              1),
('5.1',   'COSTO DE VENTAS',                'Gasto',   'DEUDORA',   'Costo de Ventas',     2),
('5.1.1', 'Costo de Mercancias Vendidas',   'Gasto',   'DEUDORA',   'Costo de Ventas',     3),
('5.2',   'GASTOS DE OPERACION',            'Gasto',   'DEUDORA',   'Gastos Operacion',    2),
('5.2.1', 'Sueldos y Salarios',             'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.2', 'Alquiler de Local',              'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.3', 'Agua y Luz',                     'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.4', 'Telefono e Internet',            'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.5', 'Papeleria y Utiles (gasto)',     'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.6', 'Depreciaciones',                 'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.7', 'Publicidad y Propaganda',        'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.8', 'Combustible y Lubricantes',      'Gasto',   'DEUDORA',   'Gastos Operacion',    3),
('5.2.9', 'Cuota Patronal IGSS',            'Gasto',   'DEUDORA',   'Gastos Operacion',    3);
GO

PRINT '==========================================================';
PRINT ' ContabilidadGT creada correctamente.';
PRINT ' Tablas : 10  |  Vistas : 4  |  Cuentas : 40';
PRINT '==========================================================';
GO
