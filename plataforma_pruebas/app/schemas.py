"""
Esquemas Pydantic (v2) para validar entrada/salida de la API.

Convención:
  - *Create  -> body que envía el frontend al crear.
  - *Update  -> body para editar (campos opcionales).
  - *Out     -> forma en que la API responde (from_attributes=True).

IMPORTANTE para el frontend:
  - Las fórmulas viajan como STRING LaTeX puro en los campos `contenido`
    (bloque latex) o dentro del `enunciado` con delimitadores $...$.
    No se hace render en backend: se almacena tal cual llega desde MathLive.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import BlockType, QuestionType


# ===========================================================================
# Módulo 0 — Auth / Teacher
# ===========================================================================
class TeacherCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    email: EmailStr
    fecha_creacion: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ===========================================================================
# Módulo 0 — Course / Student
# ===========================================================================
class CourseCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)  # ej. "1° Medio A"


class CourseUpdate(BaseModel):
    """Renombrar un curso (PATCH /courses/{id})."""
    nombre: str = Field(min_length=1, max_length=120)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    teacher_id: int
    fecha_creacion: datetime


class StudentCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    identificador: str = Field(min_length=1, max_length=50)  # RUT / matrícula


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    identificador: str
    teacher_id: int


class StudentUpdate(BaseModel):
    """Editar un alumno (PATCH /students/{id})."""
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    identificador: str | None = Field(default=None, min_length=1, max_length=50)


class CourseWithStudentsOut(CourseOut):
    students: list[StudentOut] = []


# ---------------------------------------------------------------------------
# Importación masiva desde planilla Excel
# ---------------------------------------------------------------------------
class ImportRowError(BaseModel):
    fila: int
    motivo: str


class ImportResult(BaseModel):
    """Resumen de lo que ocurrió al importar la planilla."""
    filas_leidas: int
    alumnos_creados: int
    alumnos_actualizados: int
    matriculas_nuevas: int
    cursos_creados: list[str] = []
    errores: list[ImportRowError] = []


# ===========================================================================
# Módulo 1 — Bloques de contenido (estilo Google Forms)
# ===========================================================================
class QuestionBlockCreate(BaseModel):
    tipo: BlockType
    orden: int = 0
    # Para text -> texto; latex -> LaTeX puro; image -> URL de /upload/image.
    contenido: str = Field(min_length=1)
    extra: dict | None = None

    @field_validator("contenido")
    @classmethod
    def _no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El contenido del bloque no puede estar vacío.")
        return v


class QuestionBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: BlockType
    orden: int
    contenido: str
    extra: dict | None = None


# ---------------------------------------------------------------------------
# Configuración de alternativas (se guarda en Question.configuracion_extra)
# ---------------------------------------------------------------------------
class AlternativaOpcion(BaseModel):
    id: str = Field(description="Identificador corto, ej. 'a', 'b', 'c'")
    texto: str | None = None
    latex: str | None = None  # opción escrita como fórmula (opcional)


class ConfiguracionAlternativas(BaseModel):
    """
    Estructura estricta para preguntas de tipo alternativa.
    El frontend envía esto dentro de `configuracion_extra`.
    """
    multiple: bool = False  # True = selección múltiple
    opciones: list[AlternativaOpcion] = Field(min_length=2)
    correcta: list[str] = Field(
        min_length=1,
        description="IDs de las opciones correctas. Se usa para autocorrección.",
    )

    @field_validator("correcta")
    @classmethod
    def _correcta_en_opciones(cls, correctas, info):
        opciones = info.data.get("opciones", [])
        ids = {o.id for o in opciones}
        invalidas = [c for c in correctas if c not in ids]
        if invalidas:
            raise ValueError(f"Respuestas correctas no existen en opciones: {invalidas}")
        return correctas


# ===========================================================================
# Módulo 1 — Question
# ===========================================================================
class QuestionCreate(BaseModel):
    tipo: QuestionType
    orden: int = 0
    puntaje: float = Field(default=1.0, ge=0)
    # Enunciado plano opcional (puede incluir LaTeX inline entre $...$).
    enunciado: str | None = None
    lineas_desarrollo: int = Field(default=0, ge=0)
    # Bloques enriquecidos opcionales (texto/latex/imagen ordenados).
    blocks: list[QuestionBlockCreate] = []
    # Config libre. Para alternativas debe cumplir ConfiguracionAlternativas.
    configuracion_extra: dict | None = None

    @field_validator("configuracion_extra")
    @classmethod
    def _validar_alternativas(cls, cfg, info):
        # Si la pregunta es alternativa, validamos rígidamente la config.
        if info.data.get("tipo") == QuestionType.alternativa:
            if cfg is None:
                raise ValueError("Las preguntas de alternativa requieren configuracion_extra.")
            ConfiguracionAlternativas.model_validate(cfg)  # lanza si es inválida
        return cfg


class QuestionUpdate(BaseModel):
    tipo: QuestionType | None = None
    orden: int | None = None
    puntaje: float | None = Field(default=None, ge=0)
    enunciado: str | None = None
    lineas_desarrollo: int | None = Field(default=None, ge=0)
    configuracion_extra: dict | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: QuestionType
    orden: int
    puntaje: float
    enunciado: str | None
    lineas_desarrollo: int
    configuracion_extra: dict | None
    blocks: list[QuestionBlockOut] = []


# ===========================================================================
# Módulo 1 — Test
# ===========================================================================
class TestCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    course_id: int


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    titulo: str
    descripcion: str | None
    course_id: int
    teacher_id: int
    fecha_creacion: datetime


class TestUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None


class TestSummaryOut(TestOut):
    """Fila de la vista 'Pruebas pasadas'."""
    course_nombre: str
    n_preguntas: int
    puntaje_total: float
    n_generadas: int


# ---------------------------------------------------------------------------
# Generación de ejemplares (uno por alumno)
# ---------------------------------------------------------------------------
class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    student_id: int
    student_nombre: str
    student_identificador: str
    fecha_generacion: datetime


class GenerateResult(BaseModel):
    test_id: int
    titulo: str
    curso: str
    total_alumnos: int
    nuevas: int
    existentes: int
    assignments: list[AssignmentOut] = []


class TestExportOut(TestOut):
    """Prueba completa con todas sus preguntas anidadas (para PDF / web)."""
    questions: list[QuestionOut] = []


# ===========================================================================
# Módulo 1 — Subida de imágenes
# ===========================================================================
class ImageUploadOut(BaseModel):
    url: str
    filename: str
    content_type: str
