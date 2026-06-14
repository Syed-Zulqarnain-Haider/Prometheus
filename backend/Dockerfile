# Prometheus API — Cloud Run container image.
# Installs the backend straight from pyproject.toml (single source of dependency
# truth, incl. openpyxl for XLSX export) and serves it with uvicorn on $PORT.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Project metadata first so `pip install .` resolves declared dependencies.
# (Dependencies come as manylinux wheels — no compiler/toolchain needed.)
COPY pyproject.toml README.md ./
COPY app ./app
# Alembic ships in the image so migrations can run via the same container
# (see DEPLOY.md: `alembic upgrade head` as a one-off Cloud Run job).
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install .

# Drop privileges — never run the service as root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Cloud Run injects $PORT (defaults to 8080); bind it explicitly.
ENV PORT=8080
EXPOSE 8080

# Shell form so ${PORT} expands; exec so uvicorn is PID 1 (clean SIGTERM).
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
