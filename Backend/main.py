import os
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_
from pathlib import Path
from datetime import datetime, timedelta
from passlib.context import CryptContext

from jose import jwt, JWTError

from typing import Dict
import json

from Backend.database import engine, get_db, Base, SessionLocal
from Backend import models
from Backend import schemas
from Backend.manager import manager, notification_manager  # ConnectionManager de SALAS (viene de manager.py)

from dotenv import load_dotenv

# Crea las tablas automáticamente si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mi Chat en Tiempo Real")

# Ruta base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

app.mount("/static", StaticFiles(directory=BASE_DIR / "Frontend"), name="static")

# Configuración de Seguridad (JWT y Passlib)
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if SECRET_KEY is None:
    raise ValueError("La variable SECRET_KEY no está definida en el archivo .env")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 horas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        # jose.JWTError cubre TODOS los casos: expirado, firma inválida, mal formado, etc.
        raise credentials_exception

    user = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if user is None:
        raise credentials_exception
    return user

async def crear_notificacion(db: Session, usuario_id: int, tipo: str, contenido: str):
    notificacion = models.Notificacion(
        usuario_id=usuario_id,
        tipo=tipo,
        contenido=contenido
    )
    db.add(notificacion)
    db.commit()

    # Contar no leídas y empujar en vivo si el usuario tiene el WebSocket de notificaciones abierto
    no_leidas = db.query(models.Notificacion).filter(
        models.Notificacion.usuario_id == usuario_id,
        models.Notificacion.leido == False
    ).count()

    await notification_manager.notificar(usuario_id, {"no_leidas": no_leidas})

# --- RUTAS DE VISTAS (HTML) ---

@app.get("/", response_class=HTMLResponse)
def cargar_login():
    ruta_html = BASE_DIR / "Frontend" / "login.html"
    with open(ruta_html, "r", encoding="utf-8") as archivo:
        return HTMLResponse(content=archivo.read(), status_code=200)

@app.get("/home", response_class=HTMLResponse)
def cargar_home():
    ruta_html = BASE_DIR / "Frontend" / "home.html"
    with open(ruta_html, "r", encoding="utf-8") as archivo:
        return HTMLResponse(content=archivo.read(), status_code=200)

@app.get("/configuracion", response_class=HTMLResponse)
def cargar_configuracion():
    ruta_html = BASE_DIR / "Frontend" / "configuracion.html"
    with open(ruta_html, "r", encoding="utf-8") as archivo:
        return HTMLResponse(content=archivo.read(), status_code=200)

@app.get("/chat-sala", response_class=HTMLResponse)
def cargar_chat_sala():
    ruta_html = BASE_DIR / "Frontend" / "chat_sala.html"
    with open(ruta_html, "r", encoding="utf-8") as archivo:
        return HTMLResponse(content=archivo.read(), status_code=200)

@app.get("/chat-privado", response_class=HTMLResponse)
def cargar_chat_privado():
    ruta_html = BASE_DIR / "Frontend" / "chat_privado.html"
    with open(ruta_html, "r", encoding="utf-8") as archivo:
        return HTMLResponse(content=archivo.read(), status_code=200)


# --- RUTAS DE API ---

@app.post("/api/register", status_code=status.HTTP_201_CREATED)
def registrar_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.Usuario).filter(models.Usuario.email == usuario.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado")
    
    hashed_pwd = hash_password(usuario.contrasena)
    nuevo_usuario = models.Usuario(
        nombre=usuario.nombre,
        email=usuario.email,
        contrasena=hashed_pwd
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return {"mensaje": "Usuario registrado exitosamente", "id": nuevo_usuario.id}

# --- LOGIN ACTUALIZADO ---
@app.post("/api/login")
def login(form_data: schemas.UsuarioLogin, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.email == form_data.email).first()
    if not user or not verify_password(form_data.contrasena, str(user.contrasena)):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    access_token = create_access_token(data={"sub": user.email, "id": user.id, "nombre": user.nombre})
    # Se agrega "id" a la respuesta JSON
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "nombre": user.nombre, 
        "id": user.id
    }

@app.get("/api/me")
def obtener_perfil(current_user: models.Usuario = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "nombre": current_user.nombre,
        "email": current_user.email
    }

@app.put("/api/me")
def actualizar_perfil(
    datos: schemas.UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    if datos.nombre and datos.nombre != current_user.nombre:
        existe = db.query(models.Usuario).filter(models.Usuario.nombre == datos.nombre).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso")
        current_user.nombre = datos.nombre
        db.commit()
        db.refresh(current_user)

    return {"id": current_user.id, "nombre": current_user.nombre, "email": current_user.email}


@app.get("/api/usuarios")
def listar_usuarios(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    usuarios = db.query(models.Usuario).filter(models.Usuario.id != current_user.id).all()
    return [{"id": u.id, "nombre": u.nombre, "email": u.email} for u in usuarios]

#  Obtener historial de mensajes privados
@app.get("/api/mensajes/{otro_usuario_id}")
def obtener_historial_privado(
    otro_usuario_id: str, 
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user)
):
    mi_id = str(current_user.id)
    mensajes = db.query(models.MensajePrivado).filter(
        or_(
            and_(models.MensajePrivado.remitente == mi_id, models.MensajePrivado.destinatario == otro_usuario_id),
            and_(models.MensajePrivado.remitente == otro_usuario_id, models.MensajePrivado.destinatario == mi_id)
        )
    ).order_by(models.MensajePrivado.id.asc()).all()

    return [
        {
            "remitente": m.remitente,
            "texto": m.texto,
            "fecha": m.fecha.isoformat() if m.fecha else None
        }
        for m in mensajes
    ]
    
# Mensajes Directos previos
@app.get("/api/conversaciones")
def listar_conversaciones(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """Devuelve solo los usuarios con quienes ya existe historial de mensajes privados."""
    mi_id = str(current_user.id)

    mensajes = db.query(models.MensajePrivado).filter(
        or_(
            models.MensajePrivado.remitente == mi_id,
            models.MensajePrivado.destinatario == mi_id
        )
    ).all()

    otros_ids = set()
    for m in mensajes:
        otro = m.destinatario if m.remitente == mi_id else m.remitente
        otros_ids.add(int(otro))

    if not otros_ids:
        return []

    usuarios = db.query(models.Usuario).filter(models.Usuario.id.in_(otros_ids)).all()
    return [{"id": u.id, "nombre": u.nombre, "email": u.email} for u in usuarios]

# --- WEBSOCKET NOTIFICACIONES ---
@app.websocket("/ws/notificaciones")
async def websocket_notificaciones(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        mi_id = payload.get("id")
        if mi_id is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await notification_manager.connect(websocket, mi_id)

    try:
        while True:
            # No esperamos mensajes del cliente, solo mantenemos la conexión viva
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_manager.disconnect(mi_id)

# --- WEBSOCKET SALAS GRUPALES ---
@app.websocket("/ws/sala/{sala_id}")
async def websocket_endpoint(websocket: WebSocket, sala_id: int, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        mi_id = payload.get("id")
        mi_nombre = payload.get("nombre")
        if mi_id is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        es_miembro = db.query(models.SalaMiembro).filter(
            models.SalaMiembro.sala_id == sala_id,
            models.SalaMiembro.usuario_id == mi_id
        ).first()
        if not es_miembro:
            await websocket.close(code=1008)
            return
        sala = db.query(models.Sala).filter(models.Sala.id == sala_id).first()
        nombre_sala = sala.nombre if sala else "una sala"
    finally:
        db.close()

    await manager.connect(websocket, sala_id, mi_id)

    try:
        while True:
            data = await websocket.receive_json()
            texto = data.get("mensaje")
            if not texto or not texto.strip():
                continue

            db = SessionLocal()
            try:
                nuevo_mensaje = models.Mensaje(
                    sala_id=sala_id,
                    emisor_id=mi_id,
                    contenido=texto
                )
                db.add(nuevo_mensaje)
                db.commit()

                # Notificar a los miembros de la sala que NO están conectados ahora mismo
                conectados = manager.usuarios_conectados(sala_id)
                miembros = db.query(models.SalaMiembro).filter(
                    models.SalaMiembro.sala_id == sala_id
                ).all()

                for miembro in miembros:
                    if miembro.usuario_id != mi_id and miembro.usuario_id not in conectados:
                        await crear_notificacion(
                            db,
                            miembro.usuario_id,
                            "mensaje_sala",
                            f"{mi_nombre} escribió en '{nombre_sala}': \"{texto[:50]}\""
                        )
            finally:
                db.close()

            await manager.broadcast(
                {"usuario": mi_nombre, "mensaje": texto},
                sala_id
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket, sala_id)

@app.post("/api/salas")
async def crear_sala(sala: schemas.SalaCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    nombre_limpio = sala.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre de la sala no puede estar vacío")

    # Verificar si este usuario ya tiene otra sala con el mismo nombre
    sala_existente = db.query(models.Sala).join(models.SalaMiembro).filter(
        models.SalaMiembro.usuario_id == current_user.id,
        models.Sala.nombre == nombre_limpio
    ).first()

    if sala_existente:
        raise HTTPException(status_code=400, detail="Ya tienes una sala con ese nombre")

    nueva_sala = models.Sala(
        nombre=nombre_limpio,
        descripcion=sala.descripcion,
        privado=sala.privado or False
    )
    db.add(nueva_sala)
    db.commit()
    db.refresh(nueva_sala)

    miembros_ids = set(sala.miembros_ids)
    miembros_ids.add(current_user.id)

    for usuario_id in miembros_ids:
        db.add(models.SalaMiembro(sala_id=nueva_sala.id, usuario_id=usuario_id))
    db.commit()

    # Notificar a los miembros agregados (no al creador)
    for usuario_id in miembros_ids:
        if usuario_id != current_user.id:
            await crear_notificacion(
                db,
                usuario_id,
                "sala_invitacion",
                f"{current_user.nombre} te agregó a la sala '{nueva_sala.nombre}'"
            )

    return {"mensaje": "Sala creada exitosamente", "id": nueva_sala.id}

@app.get("/api/salas")
def listar_mis_salas(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    salas = (
        db.query(models.Sala)
        .join(models.SalaMiembro, models.SalaMiembro.sala_id == models.Sala.id)
        .filter(models.SalaMiembro.usuario_id == current_user.id)
        .all()
    )
    return [
        {"id": s.id, "nombre": s.nombre, "descripcion": s.descripcion}
        for s in salas
    ]


@app.get("/api/salas/{sala_id}/mensajes")
def obtener_historial_sala(
    sala_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    es_miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a esta sala")

    mensajes = (
        db.query(models.Mensaje)
        .filter(models.Mensaje.sala_id == sala_id)
        .order_by(models.Mensaje.id.asc())
        .all()
    )
    return [
        {
            "usuario_id": m.emisor_id,
            "nombre_usuario": m.emisor.nombre if m.emisor else "Usuario eliminado",
            "mensaje": m.contenido,
            "fecha": m.fecha_creacion.isoformat() if m.fecha_creacion else None
        }
        for m in mensajes
    ]

@app.get("/api/salas/{sala_id}/miembros")
def listar_miembros_sala(
    sala_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """Devuelve los miembros actuales de una sala (solo si perteneces a ella)."""
    es_miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a esta sala")

    miembros = (
        db.query(models.Usuario)
        .join(models.SalaMiembro, models.SalaMiembro.usuario_id == models.Usuario.id)
        .filter(models.SalaMiembro.sala_id == sala_id)
        .all()
    )
    return [{"id": u.id, "nombre": u.nombre, "email": u.email} for u in miembros]


@app.post("/api/salas/{sala_id}/miembros")
async def agregar_miembros_sala(
    sala_id: int,
    payload: schemas.MiembrosAgregar,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """Agrega uno o más miembros nuevos a una sala existente."""
    es_miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a esta sala")

    sala = db.query(models.Sala).filter(models.Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada")

    ya_miembros = {
        m.usuario_id for m in db.query(models.SalaMiembro)
        .filter(models.SalaMiembro.sala_id == sala_id).all()
    }

    agregados = []
    for usuario_id in payload.miembros_ids:
        if usuario_id in ya_miembros:
            continue
        db.add(models.SalaMiembro(sala_id=sala_id, usuario_id=usuario_id))
        agregados.append(usuario_id)

    db.commit()

    for usuario_id in agregados:
        await crear_notificacion(
            db,
            usuario_id,
            "sala_invitacion",
            f"{current_user.nombre} te agregó a la sala '{sala.nombre}'"
        )

    return {"mensaje": f"{len(agregados)} miembro(s) agregado(s)"}

@app.delete("/api/salas/{sala_id}/salir")
def salir_de_sala(
    sala_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """El usuario actual abandona la sala. Si queda vacía, se borra por completo."""
    miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()

    if not miembro:
        raise HTTPException(status_code=404, detail="No perteneces a esta sala")

    db.delete(miembro)
    db.commit()

    miembros_restantes = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id
    ).count()

    if miembros_restantes == 0:
        sala = db.query(models.Sala).filter(models.Sala.id == sala_id).first()
        if sala:
            db.delete(sala)
            db.commit()
        return {"mensaje": "Has salido de la sala. Como quedó vacía, se eliminó por completo."}

    return {"mensaje": "Has salido de la sala"}

@app.get("/api/salas/{sala_id}")
def obtener_sala(
    sala_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """Devuelve los datos de una sala específica (para precargar el nombre real al editar)."""
    es_miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a esta sala")

    sala = db.query(models.Sala).filter(models.Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada")

    return {"id": sala.id, "nombre": sala.nombre, "descripcion": sala.descripcion}


@app.put("/api/salas/{sala_id}")
def renombrar_sala(
    sala_id: int,
    datos: schemas.SalaRename,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """Cambia el nombre de una sala (cualquier miembro puede hacerlo, por ahora)."""
    es_miembro = db.query(models.SalaMiembro).filter(
        models.SalaMiembro.sala_id == sala_id,
        models.SalaMiembro.usuario_id == current_user.id
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a esta sala")

    sala = db.query(models.Sala).filter(models.Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada")

    nombre_nuevo = datos.nombre.strip()
    if not nombre_nuevo:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    # Verificar si el usuario ya tiene OTRA sala con este mismo nombre
    sala_duplicada = db.query(models.Sala).join(models.SalaMiembro).filter(
        models.SalaMiembro.usuario_id == current_user.id,
        models.Sala.nombre == nombre_nuevo,
        models.Sala.id != sala_id
    ).first()

    if sala_duplicada:
        raise HTTPException(status_code=400, detail="Ya tienes otra sala con ese nombre")

    sala.nombre = nombre_nuevo
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al actualizar el nombre")
    
    db.refresh(sala)

    return {"mensaje": "Nombre actualizado", "nombre": sala.nombre}



@app.get("/api/notificaciones")
def listar_notificaciones(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    notificaciones = (
        db.query(models.Notificacion)
        .filter(models.Notificacion.usuario_id == current_user.id)
        .order_by(models.Notificacion.fecha_creacion.desc())
        .limit(30)
        .all()
    )
    return [
        {
            "id": n.id,
            "tipo": n.tipo,
            "contenido": n.contenido,
            "leido": n.leido,
            "fecha_creacion": n.fecha_creacion.isoformat() if n.fecha_creacion else None
        }
        for n in notificaciones
    ]


@app.put("/api/notificaciones/{notificacion_id}/leer")
def marcar_notificacion_leida(
    notificacion_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    notificacion = db.query(models.Notificacion).filter(
        models.Notificacion.id == notificacion_id,
        models.Notificacion.usuario_id == current_user.id
    ).first()

    if not notificacion:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")

    notificacion.leido = True
    db.commit()
    return {"mensaje": "Notificación marcada como leída"}


@app.put("/api/notificaciones/leer-todas")
def marcar_todas_leidas(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    db.query(models.Notificacion).filter(
        models.Notificacion.usuario_id == current_user.id,
        models.Notificacion.leido == False
    ).update({"leido": True})
    db.commit()
    return {"mensaje": "Todas las notificaciones marcadas como leídas"}

# --- WEBSOCKET MENSAJES PRIVADOS ---

class PrivateConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, username: str):
        self.active_connections.pop(username, None)

    async def send_personal_message(self, message: dict, target_user: str):
        websocket = self.active_connections.get(target_user)
        if websocket:
            await websocket.send_json(message)

private_manager = PrivateConnectionManager()

@app.websocket("/ws/privado")
async def websocket_privado(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        mi_id = str(payload.get("id"))
        mi_nombre = payload.get("nombre")
        if not mi_id or mi_id == "None":
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await private_manager.connect(websocket, mi_id)

    try:
        while True:
            data = await websocket.receive_json()
            destinatario_id = str(data.get("destinatario_id"))
            texto = data.get("texto")

            if not texto or not texto.strip():
                continue

            db = SessionLocal()
            try:
                nuevo_mensaje = models.MensajePrivado(
                    remitente=mi_id,
                    destinatario=destinatario_id,
                    texto=texto,
                )
                db.add(nuevo_mensaje)
                db.commit()

                # Notificar solo si el destinatario NO está viendo el chat en este momento
                if destinatario_id not in private_manager.active_connections:
                    await crear_notificacion(
                        db,
                        int(destinatario_id),
                        "mensaje_privado",
                        f"{mi_nombre} te envió un mensaje: \"{texto[:50]}\""
                    )
            finally:
                db.close()

            paquete = {"remitente_id": mi_id, "texto": texto}
            await private_manager.send_personal_message(paquete, destinatario_id)

    except WebSocketDisconnect:
        private_manager.disconnect(mi_id)

