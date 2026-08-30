# Plataforma de Pruebas — Módulo 0 + Módulo 1

Aplicación web para profesores: gestión de cursos y alumnos (con carga desde
Excel), creador de pruebas por bloques con soporte de LaTeX e imágenes, vista
previa de la hoja impresa y generación de un ejemplar único por alumno.

## Puesta en marcha (sin instalar base de datos)

Usa **SQLite** por defecto (archivo `pruebas.db`). Solo necesitas Python:

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abre **http://localhost:8000** → la aplicación.
Docs de la API (Swagger): **http://localhost:8000/docs**

Como el frontend se sirve desde el propio backend, comparten origen y no hay
problemas de CORS.

## Estructura

```
plataforma_pruebas/
├── app/
│   ├── main.py            # App FastAPI: sirve la SPA en "/" y la API
│   ├── config.py          # Settings (variables de entorno)
│   ├── database.py        # Engine, Session, Base, get_db
│   ├── models.py          # ORM: Teacher, Course, Student, Test, Question,
│   │                      #      QuestionBlock, TestAssignment
│   ├── schemas.py         # Esquemas Pydantic (validación de entrada/salida)
│   ├── security.py        # Hash de contraseñas (bcrypt) + JWT
│   ├── dependencies.py    # get_current_teacher (guardián de autenticación)
│   ├── routers/
│   │   ├── auth.py        # registro / login
│   │   ├── courses.py     # cursos, alumnos, importación Excel
│   │   ├── tests.py       # pruebas, preguntas, export, generación
│   │   └── uploads.py     # subida de imágenes
│   └── services/
│       ├── excel.py       # lectura/creación de planillas (openpyxl)
│       └── storage.py     # almacenamiento de imágenes + reintentos
├── frontend/
│   └── index.html         # Aplicación completa (login + sidebar)
├── requirements.txt
└── .env.example
```

## La aplicación

**Login / Crear cuenta.** Una sola pantalla: el fondo y la tarjeta no cambian,
solo se reemplaza el formulario al alternar entre las dos pestañas.

Tras entrar, el sidebar tiene tres secciones:

### 🎓 Cursos y Alumnos
- Crear, **renombrar** y **eliminar** cursos.
- **Carga desde Excel**: planilla con tres columnas — `nombre`, `rut`, `curso`.
  Hay un botón para descargar la plantilla ya formateada. Se puede arrastrar el
  archivo o elegirlo.
  - Los cursos que no existan **se crean solos** a partir de la columna `curso`.
  - Los alumnos se identifican por RUT: si ya existen, se reutilizan y solo se
    matriculan (un alumno puede estar en varios cursos sin duplicarse).
  - Las filas con errores **no abortan la carga**: se reportan por número de
    fila para corregirlas después.
  - Volver a subir la misma planilla no duplica nada.
- Alta manual, edición y baja de alumnos.

### 📝 Crear Prueba
- Se elige curso y título, y se arma la prueba por bloques.
- **Bloques ordenables** de tres tipos, combinables libremente (estilo Google
  Forms): texto, **fórmula LaTeX** (con vista previa en vivo vía KaTeX) e
  **imagen** (se sube y queda su URL).
- Alternativas con opciones en texto o fórmula, marcando la correcta (queda
  lista la autocorrección del Módulo 4/5). Para desarrollo se define el puntaje
  y las líneas a imprimir.
- **Vista previa**: muestra la hoja tal como se imprimirá, con el encabezado
  rígido (alumno, curso, profesor, fecha), las anclas de las esquinas y el
  espacio del QR (Módulo 3).
- **Generar prueba**: crea un ejemplar único por cada alumno del curso, con su
  código para el QR. Es idempotente: si agregas alumnos y vuelves a generar,
  los ejemplares ya impresos conservan su código.

### 🗂️ Pruebas pasadas
Historial con curso, fecha, nº de preguntas, puntaje total y ejemplares
generados. Permite abrir una prueba para seguir editándola, ver los códigos
generados por alumno, o eliminarla.

## Endpoints principales

| Método | Ruta | Para qué |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | cuenta y JWT |
| GET/POST | `/courses/` | listar (con alumnos) / crear curso |
| PATCH/DELETE | `/courses/{id}` | renombrar / eliminar curso |
| GET | `/courses/import/template` | descargar plantilla .xlsx |
| POST | `/courses/import` | carga masiva desde Excel |
| POST/DELETE | `/courses/{id}/students[/{sid}]` | matricular / quitar alumno |
| PATCH | `/courses/students/{sid}` | editar alumno |
| GET/POST | `/tests/` | historial con resumen / crear prueba |
| POST/DELETE | `/tests/{id}/questions[/{qid}]` | agregar / eliminar pregunta |
| GET | `/tests/{id}/export` | JSON anidado (PDF y web) |
| POST | `/tests/{id}/generate` | un ejemplar por alumno |
| GET | `/tests/{id}/assignments` | ejemplares generados |
| POST | `/upload/image` | subir imagen, devuelve URL |

## Notas técnicas

**LaTeX**: se guarda como string puro (tal como lo entrega MathLive/Symbolab).
El backend no renderiza; el frontend usa KaTeX y el PDF lo hará después.

**Reintentos de subida**: el requisito de "esperar 10 min y reintentar" está en
`services/storage.py` como reintento **asíncrono** con backoff (no bloquea el
servidor). Para esperas largas queda `enqueue_upload_retry` como punto de
integración con un worker (Celery/RQ/ARQ). Ver la nota en ese archivo.

**JSON portable**: JSONB en PostgreSQL, JSON en SQLite. No hay que tocar nada
al cambiar de motor.

## Cambiar a PostgreSQL (producción)
1. Descomenta `psycopg[binary]` en `requirements.txt` e instálalo.
2. En `.env`: `DATABASE_URL=postgresql+psycopg://usuario:pass@localhost:5432/pruebas`
3. Reemplaza `Base.metadata.create_all` por migraciones **Alembic**.
4. Restringe `allow_origins` del CORS al dominio real.
