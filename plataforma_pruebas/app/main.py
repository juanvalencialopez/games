"""
Punto de entrada de la aplicación FastAPI.

Ensambla routers, configura CORS, sirve las imágenes locales y crea las
tablas en desarrollo.

Ejecutar en desarrollo:
    uvicorn app.main:app --reload

Docs interactivas: http://localhost:8000/docs
"""
import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import auth, courses, tests, uploads

# ---------------------------------------------------------------------------
# Creación de tablas (solo dev). En producción usar Alembic (migraciones).
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Plataforma de Pruebas — API",
    version="0.1.0",
    description="Módulo 0 (Sesiones y Gestión Escolar) + Módulo 1 (Creador de Pruebas).",
)

# CORS: ajusta allow_origins al dominio real del frontend en producción.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir imágenes guardadas localmente en /static/uploads/...
os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)
app.mount(
    "/static/uploads",
    StaticFiles(directory=settings.LOCAL_STORAGE_DIR),
    name="uploads",
)

# Routers
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(tests.router)
app.include_router(uploads.router)


@app.get("/health", tags=["Health"])
def health():
    """Chequeo de estado. El frontend lo usa para el indicador de conexión."""
    return {"status": "ok", "service": "plataforma-pruebas"}


# Interfaz web del profesor (single-page). Se sirve desde el propio backend,
# así comparte origen con la API y no hay problemas de CORS.
_APP_HTML = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@app.get("/", include_in_schema=False)
def home():
    if _APP_HTML.exists():
        return FileResponse(_APP_HTML)
    return {"detail": "frontend/index.html no encontrado. Revisa la carpeta del proyecto."}
