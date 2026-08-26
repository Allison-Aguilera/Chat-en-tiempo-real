import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Obtiene la URL y le indicamos a Pylance que estamos seguros de que existe
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("La variable DATABASE_URL no está definida en el archivo .env")

# A partir de aquí, Pylance ya sabe que DATABASE_URL es estrictamente un string (str)
engine = create_engine(DATABASE_URL)

# Crea la fábrica de sesiones para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para definir los modelos ORM
Base = declarative_base()


# Dependencia para inyectar la sesión de base de datos en las rutas de FastAPI
def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()