FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY api/app/ ./app/
EXPOSE 8000
# Render inyecta $PORT; en local cae a 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
