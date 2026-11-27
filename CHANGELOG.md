# Changelog

Alle wichtigen Änderungen an VANTA werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- Verschlüsselung nach Sensibilitätsstufen (server/crypto.py): Stufe 1 unverschlüsselt, Stufe 2 und 3 mit AES-256-GCM und getrennten Schlüsseldateien, Schlüsselversion im Wert gespeichert, Schlüssel pro Nutzer abgeleitet, klare Fehlermeldung bei fehlendem Schlüssel, Anleitung in docs/VERSCHLUESSELUNG.md; neue Abhängigkeit cryptography
- CI: Datenbank-Service (TimescaleDB) für die Datenbanktests, Lauf auch bei Pushes auf Claude-Branches
- Workflow, der für Claude-Branches automatisch einen Pull Request erstellt
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
- Datenmodell Version 1 (Nutzer, Datenquellen, Rohdaten, Zeitreihen als TimescaleDB-Hypertable, Feedback, Protokoll) mit Alembic-Migration 0002 und Tests; Datenbanktests laufen nur mit VANTA_TEST_DATABASE_URL (neue Dev-Abhängigkeit psycopg, nur für diese Tests)
- Warteschlange auf PostgreSQL-Basis (FOR UPDATE SKIP LOCKED) mit Fehlerwarteschlange, Wiederholung mit steigender Wartezeit, Fehlerzähler und Fehlerverlauf, idempotenter Aufnahme (erst Rohdaten, dann Auftrag in einer Transaktion), Migration 0003 und Tests
- docs/SETUP.md und Vorlage für den CI-Workflow (docs/ci-workflow.yml)
- App-Grundgerüst (SwiftUI) mit Startbildschirm und Beispieldaten, Serveradresse als Einstellung, xcconfig-Vorlage, App-Icon, Build-Workflow (.github/workflows/app-build.yml) und Anleitung für SideStore (docs/APP.md); neue Build-Abhängigkeit XcodeGen, damit kein Xcode-Projekt von Hand gepflegt werden muss
