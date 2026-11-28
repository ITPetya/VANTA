# Lokale Einrichtung

Kurze Anleitung, um den VANTA-Server lokal zum Entwickeln zu starten. Die Einrichtung des echten Servers (Debian, Tailscale, Docker, Backup) steht in [SERVER-SETUP.md](SERVER-SETUP.md).

## Voraussetzungen

- Docker mit Docker Compose
- Python 3.12 (nur für Entwicklung, Tests und Migrationen außerhalb von Docker)

## Konfiguration

```bash
cp .env.example .env
```

In der `.env` mindestens `POSTGRES_PASSWORD` setzen. Die Datei niemals einchecken.

## Server und Datenbank mit Docker starten

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

- Die Datenbank (PostgreSQL mit TimescaleDB und pgvector) ist nur im internen Docker-Netz erreichbar.
- Die API lauscht nur auf `127.0.0.1:8000`.
- Prüfen: `curl http://127.0.0.1:8000/internal/health` liefert `{"status":"ok"}`.

## Entwicklung ohne Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Prüfungen, die auch in der CI laufen:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

API lokal starten:

```bash
uvicorn server.api.main:app --reload
```

## Datenbankmigrationen

Beim Start mit Docker Compose bringt der einmalige Dienst `migrate` das Schema automatisch auf den neuesten Stand (`alembic upgrade head`). Die API startet erst danach.

Neue Migration anlegen (in der Entwicklungsumgebung):

```bash
alembic -c server/db/alembic.ini revision -m "kurze beschreibung"
```

## Datenbanktests

Die Tests der Migration und Constraints laufen nur, wenn `VANTA_TEST_DATABASE_URL` gesetzt ist
(PostgreSQL mit TimescaleDB, Treiber `postgresql+psycopg`). Der Test löscht das Schema `public`,
deshalb nur eine leere Wegwerf-Datenbank verwenden, nie die echte.
