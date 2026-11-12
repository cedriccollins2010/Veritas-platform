FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Le conteneur ne tourne pas en root.
RUN useradd --create-home --uid 1000 veritas && chown -R veritas /app
USER veritas

EXPOSE 8000

# Applique les migrations puis démarre l'API.
# Les migrations sont lancées par le service « migrate » de Docker Compose, avec le
# compte propriétaire ; ce conteneur ne connaît que le compte de l'API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
