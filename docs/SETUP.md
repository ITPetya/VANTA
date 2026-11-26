# Lokale Einrichtung

Kurze Anleitung, um den VANTA-Server lokal zu starten.

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

Die Migrationen liegen in `server/db/migrations/`. Läuft die Datenbank im Docker-Netz, muss sie
für Migrationen vom Host aus erreichbar sein. Dafür `POSTGRES_HOST` in der `.env` passend setzen
(außerhalb von Docker z. B. `localhost`) und die Datenbank vorübergehend lokal freigeben. Im
Betrieb bleibt der Datenbankport unveröffentlicht.

```bash
alembic -c server/db/alembic.ini upgrade head
alembic -c server/db/alembic.ini revision -m "kurze beschreibung"
```

Die erste Migration ist bewusst leer. Das Datenmodell folgt mit dem nächsten Issue.

## CI-Workflow aktivieren

Claude darf keine Dateien unter `.github/workflows/` ändern. Die Vorlage liegt deshalb in
`docs/ci-workflow.yml` und muss einmalig manuell übernommen werden:

```bash
cp docs/ci-workflow.yml .github/workflows/ci.yml
```

Danach führt jeder Pull Request ruff, mypy und pytest aus.

## Datenbanktests

Die Tests der Migration und Constraints laufen nur, wenn `VANTA_TEST_DATABASE_URL` gesetzt ist
(PostgreSQL mit TimescaleDB, Treiber `postgresql+psycopg`). Der Test löscht das Schema `public`,
deshalb nur eine leere Wegwerf-Datenbank verwenden, nie die echte.
