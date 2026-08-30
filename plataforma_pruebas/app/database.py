"""
Configuración de SQLAlchemy 2.0: engine, sesión y Base declarativa.

`get_db` es la dependencia que inyectamos en los endpoints de FastAPI para
obtener una sesión por request y cerrarla automáticamente al finalizar.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# SQLite necesita check_same_thread=False al usarse con el pool de FastAPI.
_connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# pool_pre_ping evita usar conexiones muertas del pool (útil en producción).
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# SQLite ignora las claves foráneas salvo que se activen por conexión. Sin
# esto, los ON DELETE CASCADE no se aplicarían en desarrollo (PostgreSQL sí
# los aplica siempre).
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    """Base declarativa de la que heredan todos los modelos ORM."""
    pass


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: entrega una sesión y garantiza su cierre."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
