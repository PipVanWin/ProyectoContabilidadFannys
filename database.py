# database.py
# Configura el motor de base de datos y la sesión.
# Todos los routers importan "get_db" para obtener una conexión.

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DB_SERVER, DB_NAME, DB_DRIVER

# Cadena de conexión para SQL Server con pyodbc
CONNECTION_STRING = (
    f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}"
    f"?driver={DB_DRIVER.replace(' ', '+')}"
    f"&trusted_connection=yes"
)

# El motor es el punto central de comunicación con la BD
# pool_pre_ping=True verifica que la conexión siga viva antes de usarla
engine = create_engine(CONNECTION_STRING, pool_pre_ping=True)

# Fábrica de sesiones: cada request recibe su propia sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base que heredarán todos los modelos ORM
class Base(DeclarativeBase):
    pass

# Generador de sesión — se usa como dependencia en los routers
# FastAPI lo llama al inicio de cada request y cierra la sesión al final
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
