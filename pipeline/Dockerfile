# Pipeline analitico. Python 3.11 fijo para todos: el entorno local del lider
# es 3.9 y eso ya rompio anotaciones tipo `str | None`, que 3.9 evalua en
# tiempo de definicion. Docker elimina esa clase de bug del equipo.
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY pipeline/requirements.txt ./pipeline/requirements.txt
RUN pip install -r pipeline/requirements.txt

FROM deps AS final
COPY pipeline/ ./pipeline/
COPY sql/ ./sql/
COPY tests/ ./tests/
# data/ se monta como volumen: los JSONL crudos pesan ~740 MB y no van en la imagen
VOLUME ["/app/data"]
CMD ["python", "pipeline/build.py"]
