# config.py
# Lee las variables de entorno desde el archivo .env
# Nunca pongan contraseñas directamente en el código

from dotenv import load_dotenv
import os

load_dotenv()  # carga el archivo .env automáticamente

# Datos de conexión a SQL Server
DB_SERVER   = os.getenv("DB_SERVER",   ".")
DB_NAME     = os.getenv("DB_NAME",     "ContabilidadGT")
DB_DRIVER   = os.getenv("DB_DRIVER",   "ODBC Driver 17 for SQL Server")

# Datos de la empresa (precargados)
EMPRESA_NOMBRE      = "Fannys Express"
EMPRESA_NIT         = "327527-J"
EMPRESA_MUNICIPIO   = "Totonicapán"
EMPRESA_DEPTO       = "Totonicapán"
EMPRESA_DIRECCION   = "2da calle 8 - 28 zona 2"

# IVA Guatemala
TASA_IVA = 0.12
