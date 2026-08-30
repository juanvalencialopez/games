"""
Router de autenticación (Módulo 0).

Endpoints:
  POST /auth/register  -> crea un profesor.
  POST /auth/login     -> devuelve un JWT (access_token).

Interacción con el frontend:
  1) El usuario se registra (register) o inicia sesión (login).
  2) Guarda el `access_token` (ej. en memoria / httpOnly cookie).
  3) En TODA petición protegida envía el header:
         Authorization: Bearer <access_token>
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=schemas.TeacherOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.TeacherCreate, db: Session = Depends(get_db)):
    """Registra un nuevo profesor. Falla si el email ya existe."""
    exists = db.scalar(select(models.Teacher).where(models.Teacher.email == payload.email))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El email ya está registrado")

    teacher = models.Teacher(
        nombre=payload.nombre,
        email=payload.email,
        password_hash=hash_password(payload.password),  # nunca guardamos texto plano
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Login compatible con OAuth2 password flow (así funciona el botón
    'Authorize' de /docs).

    El frontend debe enviar los datos como form-data:
        username=<email>&password=<password>
    (el campo se llama `username` por el estándar OAuth2, pero contiene el email).
    """
    teacher = db.scalar(select(models.Teacher).where(models.Teacher.email == form.username))
    if not teacher or not verify_password(form.password, teacher.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=teacher.id)
    return schemas.Token(access_token=token)
