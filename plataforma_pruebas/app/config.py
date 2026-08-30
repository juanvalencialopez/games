"""
Configuración central de la aplicación.

Todos los valores sensibles (SECRET, credenciales de BD, credenciales S3)
se leen desde variables de entorno o del archivo .env (ver .env.example).
Nunca hardcodees secretos en el código.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Base de datos ----
    # Por defecto SQLite (archivo local, cero instalación) para probar rápido.
    # Para producción usa PostgreSQL, ej.:
    #   postgresql+psycopg://usuario:password@host:5432/basedatos
    DATABASE_URL: str = "sqlite+pysqlite:///./pruebas.db"

    # ---- Seguridad / JWT ----
    JWT_SECRET_KEY: str = "CAMBIAME_POR_UN_SECRETO_LARGO_Y_ALEATORIO"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # ---- Almacenamiento de imágenes ----
    # Estrategia de storage: "local" (disco) o "s3" (bucket).
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "./storage/uploads"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Credenciales/nombre de bucket S3 (solo si STORAGE_BACKEND == "s3")
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None

    # ---- Política de reintentos para la subida a servicios externos ----
    # OJO (decisión de arquitectura): un bloqueo síncrono de 10 min por request
    # es un anti-patrón. Aquí el reintento se hace de forma ASÍNCRONA (no
    # bloquea el event loop) y con backoff. Ver services/storage.py.
    UPLOAD_MAX_RETRIES: int = 5
    UPLOAD_RETRY_DELAY_SECONDS: int = 600  # 10 min: cumple el requisito, pero léelo con la nota anterior
    UPLOAD_RETRY_BACKOFF: float = 1.0      # 1.0 = delay fijo; >1.0 = backoff exponencial


settings = Settings()
