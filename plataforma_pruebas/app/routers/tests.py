"""
Router del Creador de Pruebas (Módulo 1).

Endpoints:
  POST   /tests/                          crear prueba
  GET    /tests/                          listar pruebas con resumen ("Pruebas pasadas")
  PATCH  /tests/{id}                      editar título/descripción
  DELETE /tests/{id}                      eliminar prueba
  POST   /tests/{id}/questions            añadir pregunta (bloques y/o alternativas)
  DELETE /tests/{id}/questions/{qid}      eliminar pregunta
  POST   /tests/{id}/questions/reorder    reordenar preguntas
  GET    /tests/{id}/export               JSON completo anidado (para PDF / web)
  POST   /tests/{id}/generate             generar un ejemplar por alumno del curso
  GET    /tests/{id}/assignments          listar ejemplares generados

Interacción con el frontend (puntos clave):
  * FÓRMULAS (LaTeX): el editor tipo Symbolab (MathLive/MathQuill) entrega un
    string LaTeX puro. Se envía como:
        - un bloque {"tipo":"latex","contenido":"\\frac{a}{b}"}, o
        - dentro de `enunciado` con delimitadores $...$.
    El backend NO renderiza: almacena el LaTeX tal cual.
  * PUNTAJES: cada pregunta lleva `puntaje` (máximo). Para alternativas, la
    clave correcta va en configuracion_extra.correcta y habilita autocorrección
    (Módulo 4/5). Para desarrollo, el puntaje se reparte luego con la rúbrica
    IA (Módulo 2) sobre este `puntaje` máximo.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_teacher

router = APIRouter(prefix="/tests", tags=["Creador de Pruebas"])


def _get_owned_test(test_id: int, teacher: models.Teacher, db: Session) -> models.Test:
    test = db.scalar(
        select(models.Test).where(
            models.Test.id == test_id,
            models.Test.teacher_id == teacher.id,
        )
    )
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prueba no encontrada")
    return test


# ---------------------------------------------------------------------------
# CRUD de pruebas
# ---------------------------------------------------------------------------
@router.post("/", response_model=schemas.TestOut, status_code=status.HTTP_201_CREATED)
def create_test(
    payload: schemas.TestCreate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Crea una prueba. Verifica que el curso pertenezca al profesor."""
    course = db.scalar(
        select(models.Course).where(
            models.Course.id == payload.course_id,
            models.Course.teacher_id == teacher.id,
        )
    )
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Curso no encontrado")

    test = models.Test(
        titulo=payload.titulo.strip(),
        descripcion=payload.descripcion,
        course_id=course.id,
        teacher_id=teacher.id,
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.get("/", response_model=list[schemas.TestSummaryOut])
def list_tests(
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Alimenta la vista "Pruebas pasadas": cada prueba con su curso, cantidad de
    preguntas, puntaje total y cuántos ejemplares se generaron.
    """
    tests = db.scalars(
        select(models.Test)
        .where(models.Test.teacher_id == teacher.id)
        .options(
            selectinload(models.Test.questions),
            selectinload(models.Test.assignments),
            selectinload(models.Test.course),
        )
        .order_by(models.Test.fecha_creacion.desc())
    ).all()

    return [
        schemas.TestSummaryOut(
            id=t.id,
            titulo=t.titulo,
            descripcion=t.descripcion,
            course_id=t.course_id,
            teacher_id=t.teacher_id,
            fecha_creacion=t.fecha_creacion,
            course_nombre=t.course.nombre if t.course else "—",
            n_preguntas=len(t.questions),
            puntaje_total=sum(q.puntaje for q in t.questions),
            n_generadas=len(t.assignments),
        )
        for t in tests
    ]


@router.patch("/{test_id}", response_model=schemas.TestOut)
def update_test(
    test_id: int,
    payload: schemas.TestUpdate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Edita el título o la descripción de una prueba."""
    test = _get_owned_test(test_id, teacher, db)
    if payload.titulo:
        test.titulo = payload.titulo.strip()
    if payload.descripcion is not None:
        test.descripcion = payload.descripcion
    db.commit()
    db.refresh(test)
    return test


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(
    test_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Elimina la prueba con sus preguntas y ejemplares generados (cascada)."""
    test = _get_owned_test(test_id, teacher, db)
    db.delete(test)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Preguntas
# ---------------------------------------------------------------------------
@router.post(
    "/{test_id}/questions",
    response_model=schemas.QuestionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_question(
    test_id: int,
    payload: schemas.QuestionCreate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Añade una pregunta a una prueba, incluyendo sus bloques de contenido
    (texto/latex/imagen) ordenados. La validación estricta de alternativas
    ocurre en el schema (QuestionCreate).

    Si el frontend no envía `orden`, la pregunta se agrega al final.
    """
    test = _get_owned_test(test_id, teacher, db)

    orden = payload.orden
    if not orden:
        actuales = db.scalars(
            select(models.Question.orden).where(models.Question.test_id == test.id)
        ).all()
        orden = (max(actuales) + 1) if actuales else 1

    question = models.Question(
        test_id=test.id,
        tipo=payload.tipo,
        orden=orden,
        puntaje=payload.puntaje,
        enunciado=payload.enunciado,
        lineas_desarrollo=payload.lineas_desarrollo,
        configuracion_extra=payload.configuracion_extra,
    )
    for b in payload.blocks:
        question.blocks.append(
            models.QuestionBlock(
                tipo=b.tipo,
                orden=b.orden,
                contenido=b.contenido,
                extra=b.extra,
            )
        )

    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/{test_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    test_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Elimina una pregunta (y sus bloques) de una prueba."""
    test = _get_owned_test(test_id, teacher, db)
    question = db.scalar(
        select(models.Question).where(
            models.Question.id == question_id,
            models.Question.test_id == test.id,
        )
    )
    if not question:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pregunta no encontrada")
    db.delete(question)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{test_id}/questions/reorder", response_model=list[schemas.QuestionOut])
def reorder_questions(
    test_id: int,
    orden_ids: list[int],
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Reordena las preguntas. El frontend envía la lista de IDs en el orden
    deseado, ej. [12, 9, 15]. Se reasigna `orden` = posición + 1.
    """
    test = _get_owned_test(test_id, teacher, db)
    preguntas = {q.id: q for q in test.questions}
    if set(orden_ids) != set(preguntas):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La lista debe contener exactamente los IDs de las preguntas de la prueba.",
        )
    for pos, qid in enumerate(orden_ids, start=1):
        preguntas[qid].orden = pos
    db.commit()
    db.refresh(test)
    return test.questions


# ---------------------------------------------------------------------------
# Export (contrato para PDF / renderizador web)
# ---------------------------------------------------------------------------
@router.get("/{test_id}/export", response_model=schemas.TestExportOut)
def export_test(
    test_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Devuelve la prueba COMPLETA con todas sus preguntas y bloques anidados,
    ordenados. Este JSON es el contrato que consumirán:
      - el generador de PDF (Módulo 3), y
      - el renderizador web (respuesta digital).

    Usamos selectinload para traer preguntas y bloques en pocas consultas
    (evita el problema N+1).
    """
    test = db.scalar(
        select(models.Test)
        .where(models.Test.id == test_id, models.Test.teacher_id == teacher.id)
        .options(
            selectinload(models.Test.questions).selectinload(models.Question.blocks)
        )
    )
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prueba no encontrada")
    return test


# ---------------------------------------------------------------------------
# Generación de ejemplares (uno por alumno del curso)
# ---------------------------------------------------------------------------
def _assignment_out(a: models.TestAssignment) -> schemas.AssignmentOut:
    return schemas.AssignmentOut(
        id=a.id,
        codigo=a.codigo,
        student_id=a.student_id,
        student_nombre=a.student.nombre,
        student_identificador=a.student.identificador,
        fecha_generacion=a.fecha_generacion,
    )


@router.post("/{test_id}/generate", response_model=schemas.GenerateResult)
def generate_test(
    test_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Botón "Generar prueba": crea un ejemplar único por cada alumno del curso
    de la prueba.

    Cada ejemplar recibe un `codigo` irrepetible que luego irá dentro del QR de
    cada página impresa (Módulo 3) y permitirá al escáner identificar prueba +
    alumno al corregir (Módulos 4 y 5).

    Es idempotente: si ya se generó para un alumno, se conserva su código y no
    se duplica. Así el profesor puede añadir alumnos nuevos y volver a generar
    sin invalidar las pruebas ya impresas.
    """
    test = db.scalar(
        select(models.Test)
        .where(models.Test.id == test_id, models.Test.teacher_id == teacher.id)
        .options(
            selectinload(models.Test.course).selectinload(models.Course.students),
            selectinload(models.Test.questions),
            selectinload(models.Test.assignments).selectinload(models.TestAssignment.student),
        )
    )
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prueba no encontrada")

    if not test.questions:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La prueba no tiene preguntas. Agrega al menos una antes de generar.",
        )

    alumnos = list(test.course.students)
    if not alumnos:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"El curso '{test.course.nombre}' no tiene alumnos. Cárgalos antes de generar.",
        )

    ya_generadas = {a.student_id for a in test.assignments}
    nuevas = 0
    for alumno in alumnos:
        if alumno.id in ya_generadas:
            continue
        # Código corto, único y legible: base del contenido del QR.
        codigo = f"T{test.id}-A{alumno.id}-{uuid.uuid4().hex[:8].upper()}"
        db.add(models.TestAssignment(test_id=test.id, student_id=alumno.id, codigo=codigo))
        nuevas += 1

    db.commit()

    assignments = db.scalars(
        select(models.TestAssignment)
        .where(models.TestAssignment.test_id == test.id)
        .options(selectinload(models.TestAssignment.student))
    ).all()
    assignments.sort(key=lambda a: a.student.nombre)

    return schemas.GenerateResult(
        test_id=test.id,
        titulo=test.titulo,
        curso=test.course.nombre,
        total_alumnos=len(alumnos),
        nuevas=nuevas,
        existentes=len(assignments) - nuevas,
        assignments=[_assignment_out(a) for a in assignments],
    )


@router.get("/{test_id}/assignments", response_model=list[schemas.AssignmentOut])
def list_assignments(
    test_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Lista los ejemplares ya generados de una prueba (alumno + código QR)."""
    _get_owned_test(test_id, teacher, db)
    assignments = db.scalars(
        select(models.TestAssignment)
        .where(models.TestAssignment.test_id == test_id)
        .options(selectinload(models.TestAssignment.student))
    ).all()
    assignments.sort(key=lambda a: a.student.nombre)
    return [_assignment_out(a) for a in assignments]
