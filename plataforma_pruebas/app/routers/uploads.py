"""
Router de subida de imágenes (Módulo 1).

POST /upload/image  -> recibe un archivo (multipart/form-data), lo almacena
                       y devuelve la URL pública para insertarla en un bloque
                       de tipo "image".

Interacción con el frontend:
  - Enviar como multipart/form-data con el campo `file`.
  - Guardar la `url` devuelta y usarla al crear el bloque:
        {"tipo": "image", "contenido": "<url>", "orden": N}
  - Requiere Authorization: Bearer <token>.

Nota de resiliencia: la lógica de reintentos ante fallo del storage externo
vive en services/storage.py (reintento asíncrono con backoff). Ver la nota de
arquitectura ahí sobre por qué NO bloqueamos el request 10 minutos.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from .. import models, schemas
from ..dependencies import get_current_teacher
from ..services import storage

router = APIRouter(prefix="/upload", tags=["Subida de imágenes"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB


@router.post("/image", response_model=schemas.ImageUploadOut)
async def upload_image(
    file: UploadFile = File(...),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Valida y almacena una imagen; devuelve su URL pública."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo no permitido: {file.content_type}",
        )

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Imagen supera 8 MB")

    try:
        stored = await storage.store_image(data, file.filename or "image.png", file.content_type)
    except storage.StorageError as exc:
        # Se agotaron los reintentos. Devolvemos 502 para que el frontend
        # informe y permita reintentar manualmente (no perdemos el proceso).
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return schemas.ImageUploadOut(
        url=stored.url, filename=stored.filename, content_type=stored.content_type
    )
