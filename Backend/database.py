import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Obtiene la URL de conexión a Neon (ahora apuntando a chat_db)
DATABASE_URL = os.getenv("DATABASE_URL")

# Crea el motor de conexión para SQLAlchemy
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