from database import Base
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship


class Usuario(Base):
  __tablename__ = "usuarios"

  id = Column(Integer, primary_key=True, index=True)
  nombre = Column(String(50), unique=True, index=True, nullable=False)
  email = Column(String(255), unique=True, index=True, nullable=False)
  contrasena = Column(String(255), nullable=False)
  fecha_creado = Column(DateTime(timezone=True), server_default=func.now())

  # Relaciones (para conectar con otras tablas fácilmente)
  mensajes = relationship("Mensaje", back_populates="emisor")
  salas_miembros = relationship("SalaMiembro", back_populates="usuario")
  notificaciones = relationship("Notificacion", back_populates="usuario")


class Sala(Base):
  __tablename__ = "salas"

  id = Column(Integer, primary_key=True, index=True)
  nombre = Column(String(100), unique=True, index=True, nullable=False)
  descripcion = Column(Text, nullable=True)
  privado = Column(Boolean, default=False)
  fecha_creado = Column(DateTime(timezone=True), server_default=func.now())

  # Relaciones
  miembros = relationship(
      "SalaMiembro", back_populates="sala", cascade="all, delete-orphan"
  )
  mensajes = relationship(
      "Mensaje", back_populates="sala", cascade="all, delete-orphan"
  )


class SalaMiembro(Base):
  __tablename__ = "salas_miembros"

  sala_id = Column(
      Integer, ForeignKey("salas.id", ondelete="CASCADE"), primary_key=True
  )
  usuario_id = Column(
      Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
  )
  fecha_unido = Column(DateTime(timezone=True), server_default=func.now())

  # Relaciones
  sala = relationship("Sala", back_populates="miembros")
  usuario = relationship("Usuario", back_populates="salas_miembros")


class Mensaje(Base):
  __tablename__ = "mensajes"

  id = Column(Integer, primary_key=True, index=True)
  sala_id = Column(
      Integer, ForeignKey("salas.id", ondelete="CASCADE"), nullable=False
  )
  emisor_id = Column(
      Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
  )
  contenido = Column(Text, nullable=False)
  fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

  # Relaciones
  sala = relationship("Sala", back_populates="mensajes")
  emisor = relationship("Usuario", back_populates="mensajes")


class Notificacion(Base):
  __tablename__ = "notificaciones"

  id = Column(Integer, primary_key=True, index=True)
  usuario_id = Column(
      Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
  )
  tipo = Column(String(50), nullable=False)
  contenido = Column(Text, nullable=False)
  leido = Column(Boolean, default=False)
  fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

  # Relaciones
  usuario = relationship("Usuario", back_populates="notificaciones")