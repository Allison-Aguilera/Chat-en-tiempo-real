from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

# --- Usuarios ---
class UsuarioCreate(BaseModel):
    nombre: str
    email: EmailStr
    contrasena: str = Field(min_length=6)

class UsuarioOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    fecha_creado: datetime

    class Config:
        from_attributes = True

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None

# --- Salas ---
class SalaCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    privado: Optional[bool] = False
    miembros_ids: List[int] = []

class SalaOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    privado: bool
    fecha_creado: datetime

    class Config:
        from_attributes = True

# --- Sala Miembros ---
class SalaMiembroCreate(BaseModel):
    sala_id: int
    usuario_id: int

class SalaMiembroOut(BaseModel):
    sala_id: int
    usuario_id: int
    fecha_unido: datetime

    class Config:
        from_attributes = True
        
class MiembrosAgregar(BaseModel):
    miembros_ids: List[int]

class SalaRename(BaseModel):
    nombre: str

# --- Mensajes ---
class MensajeCreate(BaseModel):
    contenido: str

class MensajeOut(BaseModel):
    id: int
    sala_id: int
    emisor_id: Optional[int] = None
    contenido: str
    fecha_creacion: datetime

    class Config:
        from_attributes = True

# --- Notificaciones ---
class NotificacionCreate(BaseModel):
    tipo: str
    contenido: str

class NotificacionOut(BaseModel):
    id: int
    usuario_id: int
    tipo: str
    contenido: str
    leido: bool
    fecha_creacion: datetime

    class Config:
        from_attributes = True
        
# --- Login ---
class UsuarioLogin(BaseModel):
    email: EmailStr
    contrasena: str