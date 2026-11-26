FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY server ./server
RUN pip install --no-cache-dir . && useradd --system --no-create-home vanta
USER vanta

CMD ["uvicorn", "server.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
