"""
Seguridad: hashing de contraseñas (bcrypt) y emisión/verificación de JWT.

Usamos:
  - bcrypt directamente para el hash de contraseñas.
  - PyJWT para firmar y verificar los access tokens.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


# ---------------------------------------------------------------------------
# Contraseñas
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt (con salt) de una contraseña en texto plano."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Compara una contraseña en texto plano contra su hash almacenado."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JSON Web Tokens
# ---------------------------------------------------------------------------
def create_access_token(subject: str | int, extra_claims: dict | None = None) -> str:
    """
    Crea un JWT firmado. `subject` normalmente es el teacher.id.
    El frontend debe guardar este token y enviarlo en cada request como:
        Authorization: Bearer <access_token>
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decodifica y valida el JWT. Lanza jwt.PyJWTError si es inválido/expiró."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
