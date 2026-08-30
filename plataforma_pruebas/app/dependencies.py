"""
Dependencias reutilizables de FastAPI.

`get_current_teacher` es el guardián de autenticación: extrae el JWT del
header Authorization, lo valida y devuelve el Teacher de la BD. Cualquier
endpoint que dependa de él queda protegido y "sabe" quién es el profesor.
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_access_token

# tokenUrl apunta al endpoint de login (usado por la UI de /docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o token expirado",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_teacher(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Teacher:
    """Valida el JWT y retorna el profesor autenticado."""
    try:
        payload = decode_access_token(token)
        teacher_id = payload.get("sub")
        if teacher_id is None:
            raise _credentials_exc
    except jwt.PyJWTError:
        raise _credentials_exc

    teacher = db.get(models.Teacher, int(teacher_id))
    if teacher is None:
        raise _credentials_exc
    return teacher
