FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY api/app/ ./app/
EXPOSE 8000
# Render inyecta $PORT; en local cae a 8000
# --proxy-headers/--forwarded-allow-ips: Render termina TLS en su proxy y
# reenvia por HTTP plano con X-Forwarded-Proto: https. Sin esto, uvicorn no
# sabe que la conexion original fue HTTPS y genera redirects (ej. /mcp ->
# /mcp/) con esquema http://, que el cliente MCP no puede seguir bien.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
