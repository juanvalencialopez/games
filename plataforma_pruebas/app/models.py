"""
Modelos ORM (SQLAlchemy 2.0, estilo tipado con Mapped/mapped_column).

Cubre:
  - Módulo 0: Teacher, Course, Student y la relación N:M Course<->Student.
  - Módulo 1: Test, Question y QuestionBlock (contenido tipo "Google Forms").

Nota sobre encapsulamiento (Módulo 0):
  Cada Course, Student y Test tiene `teacher_id`. Esto garantiza que todo el
  contenido pertenezca únicamente a la sesión del profesor creador. Las
  consultas SIEMPRE filtran por el profesor autenticado (ver routers/).

Nota sobre PostgreSQL / SQLite:
  Las columnas JSON usan un tipo portable (`JSONVariant`): JSONB en PostgreSQL
  (producción) y JSON genérico en SQLite (dev/pruebas rápidas). No hay que
  cambiar nada al alternar de motor.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Tipo JSON portable: usa JSONB (binario, indexable) en PostgreSQL —el motor
# de producción— y JSON genérico en otros motores como SQLite (dev/pruebas).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


# ---------------------------------------------------------------------------
# Enums de dominio
# ---------------------------------------------------------------------------
class QuestionType(str, enum.Enum):
    """Tipos de pregunta soportados por el Creador de Pruebas."""
    alternativa = "alternativa"           # selección única/múltiple
    desarrollo_corto = "desarrollo_corto"  # respuesta breve manuscrita
    desarrollo_largo = "desarrollo_largo"  # respuesta extensa manuscrita


class BlockType(str, enum.Enum):
    """
    Tipo de bloque de contenido dentro del enunciado de una pregunta.
    Permite componer el enunciado "estilo Google Forms": texto, fórmula o
    imagen, en el orden que el profesor quiera (imagen antes/después de texto,
    fórmula intercalada, etc.).
    """
    text = "text"     # texto plano / markdown ligero
    latex = "latex"   # fórmula matemática en LaTeX puro (desde MathLive)
    image = "image"   # imagen (contenido = URL devuelta por /upload/image)


# ---------------------------------------------------------------------------
# Módulo 0 — Relación N:M entre cursos y alumnos
# ---------------------------------------------------------------------------
# Un alumno puede pertenecer a varios cursos y un curso tiene varios alumnos.
# Tabla de asociación con restricción de unicidad para evitar duplicados.
course_student = Table(
    "course_student",
    Base.metadata,
    Column("course_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("student_id", ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("course_id", "student_id", name="uq_course_student"),
)


# ---------------------------------------------------------------------------
# Módulo 0 — Teacher
# ---------------------------------------------------------------------------
class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relaciones inversas
    courses: Mapped[list["Course"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")
    students: Mapped[list["Student"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")
    tests: Mapped[list["Test"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Módulo 0 — Course
# ---------------------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)  # ej. "1° Medio A"
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher: Mapped["Teacher"] = relationship(back_populates="courses")
    # N:M con alumnos vía tabla de asociación
    students: Mapped[list["Student"]] = relationship(
        secondary=course_student, back_populates="courses"
    )
    # cascade: al eliminar un curso se eliminan sus pruebas (y en cadena, sus
    # preguntas y generaciones). Los alumnos NO se borran: solo se desmatriculan.
    tests: Mapped[list["Test"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Módulo 0 — Student
# ---------------------------------------------------------------------------
class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        # Un mismo identificador (RUT/matrícula) no se repite dentro del universo
        # de alumnos de un mismo profesor.
        UniqueConstraint("teacher_id", "identificador", name="uq_teacher_student_identificador"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    identificador: Mapped[str] = mapped_column(String(50), nullable=False)  # RUT / matrícula
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)

    teacher: Mapped["Teacher"] = relationship(back_populates="students")
    courses: Mapped[list["Course"]] = relationship(
        secondary=course_student, back_populates="students"
    )


# ---------------------------------------------------------------------------
# Módulo 1 — Test
# ---------------------------------------------------------------------------
class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher: Mapped["Teacher"] = relationship(back_populates="tests")
    course: Mapped["Course"] = relationship(back_populates="tests")
    # order_by asegura que las preguntas siempre salgan ordenadas al exportar.
    questions: Mapped[list["Question"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="Question.orden",
    )
    # Ejemplares generados (uno por alumno). Ver TestAssignment.
    assignments: Mapped[list["TestAssignment"]] = relationship(
        back_populates="test", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Módulo 1 — Question
# ---------------------------------------------------------------------------
class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)

    tipo: Mapped[QuestionType] = mapped_column(SAEnum(QuestionType), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)  # posición dentro de la prueba
    puntaje: Mapped[float] = mapped_column(default=1.0)     # puntaje máximo de la pregunta

    # Enunciado "plano" (texto que puede incluir LaTeX inline con $...$).
    # Sirve para casos simples; el enunciado enriquecido va en `blocks`.
    enunciado: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cantidad de líneas a imprimir en papel para respuestas de desarrollo.
    lineas_desarrollo: Mapped[int] = mapped_column(Integer, default=0)

    # JSON flexible. Para alternativas guarda las opciones y la clave correcta:
    #   {"multiple": false, "opciones": [{"id":"a","texto":"...","latex":null}],
    #    "correcta": ["a"]}
    configuracion_extra: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    test: Mapped["Test"] = relationship(back_populates="questions")
    blocks: Mapped[list["QuestionBlock"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionBlock.orden",
    )


# ---------------------------------------------------------------------------
# Módulo 1 — QuestionBlock (contenido modular estilo Google Forms)
# ---------------------------------------------------------------------------
class QuestionBlock(Base):
    """
    Bloque de contenido de un enunciado. Una pregunta se compone de N bloques
    ordenados. Esto permite intercalar texto, fórmulas e imágenes libremente:

        [text]  "Observa la siguiente figura:"
        [image] "https://.../figura.png"
        [latex] "\\frac{a}{b} + c"
        [text]  "Calcula el resultado."
    """
    __tablename__ = "question_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)

    tipo: Mapped[BlockType] = mapped_column(SAEnum(BlockType), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    # Contenido según el tipo:
    #   text  -> texto plano
    #   latex -> LaTeX puro (ej. "\\frac{a}{b}")  <-- enviado por MathLive
    #   image -> URL de la imagen (la que devuelve POST /upload/image)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadatos opcionales (ej. {"alt": "figura 1", "width": 400}).
    extra: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    question: Mapped["Question"] = relationship(back_populates="blocks")


# ---------------------------------------------------------------------------
# Módulo 1/3 — TestAssignment (ejemplar de una prueba para un alumno)
# ---------------------------------------------------------------------------
class TestAssignment(Base):
    """
    Materializa "una prueba generada para un alumno concreto".

    El botón "Generar prueba" crea un registro por cada alumno del curso.
    `codigo` es un identificador único e irrepetible que:
      - se imprimirá dentro del QR de cada página (Módulo 3), y
      - permitirá al escáner saber qué prueba y qué alumno está corrigiendo
        (Módulos 4 y 5).
    """
    __tablename__ = "test_assignments"
    __table_args__ = (
        # Un alumno no puede tener dos ejemplares de la misma prueba.
        UniqueConstraint("test_id", "student_id", name="uq_test_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)

    codigo: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    test: Mapped["Test"] = relationship(back_populates="assignments")
    student: Mapped["Student"] = relationship()
