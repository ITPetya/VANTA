# Changelog

Alle wichtigen Änderungen an VANTA werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- App: lokale Benachrichtigungen (kein Apple Push) mit Berechtigungsanfrage, Testbriefing mit den letzten HealthKit-Werten zu Startzeiten 07:00, 12:30 und 21:00 (in den Einstellungen änderbar, 7 Tage vorab terminiert), Ruhezeiten (Startwert 22:00 bis 06:30), Feedback-Erfassung (zugestellt, geöffnet mit Zeit bis zum Öffnen, weggewischt über customDismissAction) im lokalen Zwischenspeicher mit eindeutiger ID und Status "nicht hochgeladen", Ansicht der letzten Feedback-Einträge
- App: HealthKit lesen (Schlaf, Herzfrequenz, HRV, Ruhepuls, Gewicht, Schritte, nur Lesezugriff) mit Hintergrundzustellung, lokaler SwiftData-Zwischenspeicher mit eindeutiger ID und Status "nicht hochgeladen", Ansicht mit letzten Werten, Anzahl im Zwischenspeicher, letzter Hintergrundzustellung und Hinweis bei fehlender Berechtigung; Entitlements in docs/APP.md
- Backup (server/backup): verschlüsselter Datenbank-Dump (AES-256 über openssl, Passphrase aus Schlüsseldatei), atomares Schreiben, Aufbewahrungsregel (neueste N), Meldung des Erfolgs über die Marker-Datei an die Selbstüberwachung (bei Fehler weder Meldung noch Löschen alter Backups), Entschlüsselung per `python -m server.backup decrypt`, neue Einstellungen in .env.example, Anleitung zur Wiederherstellung in docs/BACKUP.md und Tests
- Pre-Commit-Konfiguration mit gitleaks (.pre-commit-config.yaml)
- Selbstüberwachung (server/monitoring): Quellen melden ihren letzten erfolgreichen Lauf, Quelle länger still als erwartet (Intervall mal 1,5) oder nie gemeldet gilt als offline, interner Status-Endpunkt `/internal/status` (Quellen, letzter Sync, Länge von Warteschlange und Fehlerwarteschlange, letztes Backup über eine Marker-Datei), optionaler Push an Uptime Kuma pro Quelle (URLs aus .env), neue Einstellungen in .env.example und Tests; httpx ist jetzt Laufzeitabhängigkeit (Kuma-Push)
- App-Build veröffentlicht bei jedem Merge auf main ein Release mit .ipa und SideStore-Quelle (source.json), Updates direkt in SideStore; Test für den Quellen-Generator
- Verschlüsselung nach Sensibilitätsstufen (server/crypto.py): Stufe 1 unverschlüsselt, Stufe 2 und 3 mit AES-256-GCM und getrennten Schlüsseldateien, Schlüsselversion im Wert gespeichert, Schlüssel pro Nutzer abgeleitet, klare Fehlermeldung bei fehlendem Schlüssel, Anleitung in docs/VERSCHLUESSELUNG.md; neue Abhängigkeit cryptography
- CI: Datenbank-Service (TimescaleDB) für die Datenbanktests, Lauf auch bei Pushes auf Claude-Branches
- Workflow, der für Claude-Branches automatisch einen Pull Request erstellt; läuft nach jedem Lauf von Claude Code und startet die Prüfungen per workflow_dispatch, weil Claudes Commits selbst keine Workflows auslösen
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
