"""
Router de Cursos y Alumnos (Módulo 0).

Todos los endpoints están protegidos por `get_current_teacher`. Las consultas
SIEMPRE filtran por el profesor autenticado: un profesor jamás ve ni modifica
datos de otro (encapsulamiento por sesión).

Endpoints:
  POST   /courses/                          crear curso
  GET    /courses/                          listar cursos (con nº de alumnos)
  GET    /courses/{id}                      detalle del curso con sus alumnos
  PATCH  /courses/{id}                      renombrar curso
  DELETE /courses/{id}                      eliminar curso (y sus pruebas)
  POST   /courses/{id}/students             añadir alumno al curso
  DELETE /courses/{id}/students/{sid}       quitar alumno del curso
  PATCH  /courses/students/{sid}            editar datos del alumno
  GET    /courses/import/template           descargar planilla modelo (.xlsx)
  POST   /courses/import                    carga masiva desde planilla Excel
"""
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_teacher
from ..services import excel

router = APIRouter(prefix="/courses", tags=["Cursos y Alumnos"])


# ---------------------------------------------------------------------------
# Helpers de propiedad (evitan que un profesor toque datos de otro)
# ---------------------------------------------------------------------------
def _get_owned_course(course_id: int, teacher: models.Teacher, db: Session) -> models.Course:
    course = db.scalar(
        select(models.Course).where(
            models.Course.id == course_id,
            models.Course.teacher_id == teacher.id,
        )
    )
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Curso no encontrado")
    return course


def _get_owned_student(student_id: int, teacher: models.Teacher, db: Session) -> models.Student:
    student = db.scalar(
        select(models.Student).where(
            models.Student.id == student_id,
            models.Student.teacher_id == teacher.id,
        )
    )
    if not student:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Alumno no encontrado")
    return student


# ---------------------------------------------------------------------------
# Planilla Excel — descarga de plantilla e importación masiva
# ---------------------------------------------------------------------------
# NOTA: estas rutas van ANTES de "/{course_id}" para que FastAPI no interprete
# "import" como si fuera un id de curso.
@router.get("/import/template", include_in_schema=True)
def download_template(teacher: models.Teacher = Depends(get_current_teacher)):
    """
    Devuelve la planilla modelo (.xlsx) con las columnas: nombre, rut, curso.
    El frontend la ofrece como descarga antes de que el profesor cargue la suya.
    """
    data = excel.build_template_workbook()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_alumnos.xlsx"'},
    )


@router.post("/import", response_model=schemas.ImportResult)
async def import_students(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Carga masiva de alumnos desde una planilla Excel (multipart/form-data,
    campo `file`). Columnas: nombre, rut, curso.

    Comportamiento:
      - Si el curso de una fila no existe, se crea automáticamente.
      - Si el alumno (por RUT) ya existe, se reutiliza y solo se matricula
        (y se actualiza su nombre si cambió).
      - Las filas con errores no abortan la carga: se reportan al final para
        que el profesor las corrija sin perder el resto.
    """
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo debe ser una planilla Excel (.xlsx).",
        )

    raw = await file.read()
    try:
        filas, errores = excel.parse_students_workbook(raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Cachés en memoria para no consultar la BD en cada fila.
    cursos: dict[str, models.Course] = {
        c.nombre.strip().lower(): c
        for c in db.scalars(select(models.Course).where(models.Course.teacher_id == teacher.id))
    }
    alumnos: dict[str, models.Student] = {
        s.identificador.strip().lower(): s
        for s in db.scalars(select(models.Student).where(models.Student.teacher_id == teacher.id))
    }

    creados = actualizados = matriculas = 0
    cursos_creados: list[str] = []

    for fila in filas:
        clave_curso = fila["curso"].strip().lower()
        course = cursos.get(clave_curso)
        if course is None:
            course = models.Course(nombre=fila["curso"].strip(), teacher_id=teacher.id)
            db.add(course)
            db.flush()  # obtener id sin cerrar la transacción
            cursos[clave_curso] = course
            cursos_creados.append(course.nombre)

        clave_alumno = fila["identificador"].strip().lower()
        student = alumnos.get(clave_alumno)
        if student is None:
            student = models.Student(
                nombre=fila["nombre"],
                identificador=fila["identificador"],
                teacher_id=teacher.id,
            )
            db.add(student)
            db.flush()
            alumnos[clave_alumno] = student
            creados += 1
        elif student.nombre != fila["nombre"]:
            student.nombre = fila["nombre"]  # el RUT manda; corregimos el nombre
            actualizados += 1

        if student not in course.students:
            course.students.append(student)
            matriculas += 1

    db.commit()
    return schemas.ImportResult(
        filas_leidas=len(filas),
        alumnos_creados=creados,
        alumnos_actualizados=actualizados,
        matriculas_nuevas=matriculas,
        cursos_creados=cursos_creados,
        errores=[schemas.ImportRowError(**e) for e in errores],
    )


# ---------------------------------------------------------------------------
# CRUD de cursos
# ---------------------------------------------------------------------------
@router.post("/", response_model=schemas.CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Crea un curso asociado al profesor logueado."""
    course = models.Course(nombre=payload.nombre.strip(), teacher_id=teacher.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/", response_model=list[schemas.CourseWithStudentsOut])
def list_courses(
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Lista los cursos del profesor con sus alumnos anidados.
    selectinload evita el problema N+1 al traer los alumnos.
    """
    return db.scalars(
        select(models.Course)
        .where(models.Course.teacher_id == teacher.id)
        .options(selectinload(models.Course.students))
        .order_by(models.Course.nombre)
    ).all()


@router.get("/{course_id}", response_model=schemas.CourseWithStudentsOut)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Detalle de un curso con la lista de alumnos matriculados."""
    return _get_owned_course(course_id, teacher, db)


@router.patch("/{course_id}", response_model=schemas.CourseOut)
def rename_course(
    course_id: int,
    payload: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Renombra un curso (ej. corregir '1 Medio A' → '1° Medio A')."""
    course = _get_owned_course(course_id, teacher, db)
    course.nombre = payload.nombre.strip()
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Elimina un curso y, en cascada, sus pruebas (con preguntas y ejemplares
    generados). Los alumnos NO se eliminan: solo quedan desmatriculados, porque
    pueden pertenecer a otros cursos.
    """
    course = _get_owned_course(course_id, teacher, db)
    db.delete(course)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Alumnos
# ---------------------------------------------------------------------------
@router.post(
    "/{course_id}/students",
    response_model=schemas.StudentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_student_to_course(
    course_id: int,
    payload: schemas.StudentCreate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Añade un alumno a un curso.

    Lógica:
      - Si el alumno (por `identificador`) ya existe para este profesor,
        se reutiliza y solo se matricula en el curso (relación N:M).
      - Si no existe, se crea y se matricula.
    Esto permite que un mismo alumno esté en varios cursos sin duplicarse.
    """
    course = _get_owned_course(course_id, teacher, db)

    student = db.scalar(
        select(models.Student).where(
            models.Student.teacher_id == teacher.id,
            models.Student.identificador == payload.identificador.strip(),
        )
    )
    if student is None:
        student = models.Student(
            nombre=payload.nombre.strip(),
            identificador=payload.identificador.strip(),
            teacher_id=teacher.id,
        )
        db.add(student)
        db.flush()

    if student not in course.students:
        course.students.append(student)

    db.commit()
    db.refresh(student)
    return student


@router.delete("/{course_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_student_from_course(
    course_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """
    Quita al alumno del curso (lo desmatricula). Si ya no pertenece a ningún
    curso, se elimina del todo para no dejar registros huérfanos.
    """
    course = _get_owned_course(course_id, teacher, db)
    student = _get_owned_student(student_id, teacher, db)

    if student in course.students:
        course.students.remove(student)
        db.flush()

    if not student.courses:
        db.delete(student)

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/students/{student_id}", response_model=schemas.StudentOut)
def update_student(
    student_id: int,
    payload: schemas.StudentUpdate,
    db: Session = Depends(get_db),
    teacher: models.Teacher = Depends(get_current_teacher),
):
    """Edita el nombre y/o el RUT de un alumno."""
    student = _get_owned_student(student_id, teacher, db)

    if payload.identificador and payload.identificador.strip() != student.identificador:
        choque = db.scalar(
            select(models.Student).where(
                models.Student.teacher_id == teacher.id,
                models.Student.identificador == payload.identificador.strip(),
                models.Student.id != student.id,
            )
        )
        if choque:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Ya tienes otro alumno con ese RUT/matrícula.",
            )
        student.identificador = payload.identificador.strip()

    if payload.nombre:
        student.nombre = payload.nombre.strip()

    db.commit()
    db.refresh(student)
    return student
