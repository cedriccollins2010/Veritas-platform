FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Bibliothèque de vérification VERITAS, à côté de /app comme verifier/ à côté de backend/
# dans le dépôt : requirements.txt la désigne par « ../verifier ». Le contexte « verifier »
# est fourni par Docker Compose (additional_contexts) ; sans Compose :
#   docker build --build-context verifier=./verifier ./backend
COPY --from=verifier pyproject.toml README.md LICENSE NOTICE /verifier/
COPY --from=verifier src /verifier/src

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Le conteneur ne tourne pas en root.
RUN useradd --create-home --uid 1000 veritas && chown -R veritas /app \
    && mkdir -p /data/storage && chown veritas /data/storage && chmod 700 /data/storage
USER veritas

EXPOSE 8000

# Applique les migrations puis démarre l'API.
# Les migrations sont lancées par le service « migrate » de Docker Compose, avec le
# compte propriétaire ; ce conteneur ne connaît que le compte de l'API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
