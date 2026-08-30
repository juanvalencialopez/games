"""
Servicio de almacenamiento de imágenes.

Dos backends:
  - "local": guarda el archivo en disco (dev). Prácticamente no falla.
  - "s3": sube a un bucket. Aquí es donde aplica la política de reintentos.

------------------------------------------------------------------------------
NOTA DE ARQUITECTURA (léela antes de subir a producción)
------------------------------------------------------------------------------
El requisito pedía: "si la petición falla, esperar al menos 10 minutos y
reintentar en lugar de saltar el proceso".

Implementarlo como un `time.sleep(600)` DENTRO del request HTTP es un
anti-patrón grave:
  - Bloquea un worker/conexión durante 10 min por cada request fallido.
  - El cliente (navegador/proxy) hace timeout mucho antes (30-120 s).
  - Con pocos fallos concurrentes tumbas el servidor.

Solución adoptada (respetando el requisito de "reintentar, no saltar"):
  1. Reintento ASÍNCRONO con `asyncio.sleep` (no bloquea el event loop) y
     backoff configurable. Sirve para reintentos cortos (segundos).
  2. Para esperas largas (10+ min) lo correcto es un WORKER en background
     (Celery / RQ / ARQ). Dejo `enqueue_upload_retry` como punto de
     integración: el endpoint responde de inmediato y el reintento largo
     ocurre fuera del ciclo request/response.

Configura la política en config.py (UPLOAD_* ).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass

from ..config import settings

logger = logging.getLogger("storage")


class StorageError(Exception):
    """Error no recuperable de almacenamiento (tras agotar reintentos)."""


@dataclass
class StoredImage:
    url: str
    filename: str
    content_type: str


# ---------------------------------------------------------------------------
# Backend local (disco)
# ---------------------------------------------------------------------------
def _save_local(data: bytes, filename: str) -> str:
    os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)
    path = os.path.join(settings.LOCAL_STORAGE_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    # URL pública servida por StaticFiles (ver main.py).
    return f"{settings.PUBLIC_BASE_URL}/static/uploads/{filename}"


# ---------------------------------------------------------------------------
# Backend S3 (simulado) — punto de fallo donde aplica el reintento
# ---------------------------------------------------------------------------
async def _upload_s3_once(data: bytes, filename: str, content_type: str) -> str:
    """
    Un intento de subida a S3. Reemplaza el cuerpo por boto3 real:

        import boto3
        s3 = boto3.client("s3", region_name=settings.S3_REGION)
        s3.put_object(Bucket=settings.S3_BUCKET, Key=filename,
                      Body=data, ContentType=content_type)

    boto3 es síncrono; en async conviene ejecutarlo en un threadpool con
    `await asyncio.to_thread(...)` para no bloquear el event loop.
    """
    if not settings.S3_BUCKET:
        # Simulamos un fallo para demostrar la lógica de reintento.
        raise StorageError("S3_BUCKET no configurado (subida simulada fallida).")
    key = filename
    return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"


async def _upload_with_retry(data: bytes, filename: str, content_type: str) -> str:
    """
    Reintenta la subida a S3 con backoff. Asíncrono: NO bloquea el servidor.

    UPLOAD_MAX_RETRIES     -> nº máximo de intentos.
    UPLOAD_RETRY_DELAY_SECONDS -> espera base entre intentos.
    UPLOAD_RETRY_BACKOFF   -> factor multiplicador (1.0 = fijo).
    """
    delay = settings.UPLOAD_RETRY_DELAY_SECONDS
    last_error: Exception | None = None

    for intento in range(1, settings.UPLOAD_MAX_RETRIES + 1):
        try:
            return await _upload_s3_once(data, filename, content_type)
        except Exception as exc:  # noqa: BLE001 (queremos capturar cualquier fallo de red)
            last_error = exc
            logger.warning("Subida fallida (intento %s): %s", intento, exc)
            if intento < settings.UPLOAD_MAX_RETRIES:
                logger.info("Reintentando en %.0f s ...", delay)
                await asyncio.sleep(delay)               # no bloquea el event loop
                delay *= settings.UPLOAD_RETRY_BACKOFF   # backoff opcional

    raise StorageError(
        f"No se pudo subir '{filename}' tras {settings.UPLOAD_MAX_RETRIES} intentos"
    ) from last_error


# ---------------------------------------------------------------------------
# API pública del servicio
# ---------------------------------------------------------------------------
async def store_image(data: bytes, original_name: str, content_type: str) -> StoredImage:
    """
    Guarda una imagen y devuelve su URL. Elige backend según config.
    Genera un nombre único para evitar colisiones.
    """
    ext = os.path.splitext(original_name)[1].lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"

    if settings.STORAGE_BACKEND == "s3":
        url = await _upload_with_retry(data, filename, content_type)
    else:
        url = _save_local(data, filename)

    return StoredImage(url=url, filename=filename, content_type=content_type)


# ---------------------------------------------------------------------------
# Punto de integración para reintentos LARGOS (>= 10 min) en background.
# ---------------------------------------------------------------------------
def enqueue_upload_retry(data: bytes, filename: str, content_type: str) -> None:
    """
    Placeholder para encolar el reintento en un worker (Celery/RQ/ARQ).
    En producción, el endpoint responde de inmediato y este job reintenta
    con esperas largas sin bloquear la API. Ej. con RQ:

        from redis import Redis
        from rq import Queue
        q = Queue("uploads", connection=Redis())
        q.enqueue(upload_job, data, filename, content_type,
                  retry=Retry(max=5, interval=[600, 600, 600]))
    """
    logger.info("TODO: encolar reintento en background para %s", filename)
