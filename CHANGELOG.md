# Changelog

Alle wichtigen Änderungen an VANTA werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- Projektkonzept und Projektleitfaden (ROADMAP.md)
- README.md, SECURITY.md, CHANGELOG.md
- .gitignore und .env.example
- LICENSE (AGPL-3.0)
- config.example/ als Vorlage für die private Konfiguration
- CLAUDE.md mit Arbeitsanweisungen für Claude
- GitHub-Workflow für Claude Code (Auslösen per @claude, nur durch den Repository-Besitzer)
- Entscheidungen: Mini-PC mit Debian und Docker Compose, Cloudflare Tunnel mit Geräte-Authentifizierung, App-Build über GitHub Actions, Installation über SideStore, lokale Benachrichtigungen bis M4
- Server-Grundgerüst: Ordnerstruktur, FastAPI mit internem Health-Endpunkt, Konfiguration über .env
- deploy/docker-compose.yml mit PostgreSQL (TimescaleDB, pgvector) und API-Dienst
- Alembic mit erster leerer Migration
- pyproject.toml mit ruff, mypy und pytest
- ROADMAP: Betriebsmodell (eigene Hardware, ein bis zwei Nutzer) und Regeln für einen späteren Umzug in die Cloud, Hardware-Abschnitt aktualisiert
- CLAUDE.md: Regeln für Nutzertrennung und Portabilität
- docs/SETUP.md und Vorlage für den CI-Workflow (docs/ci-workflow.yml)
