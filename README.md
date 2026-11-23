# VANTA

**Proaktiver persönlicher KI-Assistent.**
VANTA sammelt Daten aus vielen Quellen, verknüpft sie miteinander und liefert zum richtigen Zeitpunkt, in der richtigen Form das, was wirklich wichtig ist.

> **Status:** Konzeptphase. Noch kein lauffähiger Code. Der Fahrplan steht in [ROADMAP.md](ROADMAP.md).

---

## Was VANTA tun soll

VANTA ist kein starrer Tagesbericht, sondern ein System, das mitdenkt:

- **Trends erkennen:** Schlaf, Stress, Puls oder Gewicht entwickeln sich über Wochen auffällig? VANTA merkt es und meldet es relativ zum persönlichen Normalwert.
- **Themen weiterverfolgen:** Ein gelesener Artikel bekommt Tage später eine Fortsetzung? VANTA liefert das Update.
- **Kreuzverweise herstellen:** Mail, Termin, Person und Nachricht hängen zusammen? VANTA zeigt den Zusammenhang.
- **Den richtigen Moment wählen:** Morgens beim Frühstück, in der Pause, abends. Push oder stille Anzeige, Text oder Grafik.
- **Dazulernen:** VANTA lernt aus dem Verhalten, was interessiert, was nicht und wie Informationen am besten ankommen.

## Datenquellen (geplant)

| Bereich | Quellen |
|---|---|
| Gesundheit | Schlaf, Puls, HRV, Stress, Gewicht, Schritte (HealthKit) |
| Organisation | Mail, Kalender |
| Interessen | Nachrichten, RSS, Trends, Leseverhalten |
| Verhalten | Bildschirmzeit nach Kategorie, Reaktion auf Meldungen, Standortwechsel |

## Aufbau

```
iPhone-App  ──>  Ingest  ──>  Schnellfilter  ──>  Analyse  ──>  Datenbank  ──>  Zustellplaner  ──>  iPhone-App
(Sensor und                    (Regeln,           (Batch,                     (Zeitpunkt,
 Oberfläche)                    Dringlichkeit)     Echtzeit,                   Form, Kanal)
                                                   lokal)
```

- **iOS-App:** Sensor für alles, was keine andere Schnittstelle liefert, und Oberfläche mit Briefings, Graphen und Chat.
- **Server:** läuft im eigenen Homelab. Speichert alle Daten, bewertet und verarbeitet sie und plant die Zustellung.
- **Sprachmodell:** externe API, überwiegend im günstigen Batch-Modus. Gesundheitsdaten werden nur lokal ausgewertet.

Die ausführliche Architektur steht in der [ROADMAP.md](ROADMAP.md#3-architekturüberblick).

## Grundprinzipien

1. Informationen dürfen nie fehlen.
2. Stille ist kein "alles in Ordnung". Fällt ein Sensor aus, wird das gemeldet.
3. Lernen für die Routine, feste Regeln für das Seltene und Wichtige.
4. Fehlende Daten werden offen benannt.
5. Sensible Daten werden nach Stufen getrennt und verschlüsselt. Gesundheitsdaten verlassen den Server nicht.
6. Was warten kann, wird gebündelt verarbeitet.
7. Jede Meldung kann begründen, warum sie kommt.
8. VANTA liest, handelt aber nicht ohne Bestätigung.

## Geplante Projektstruktur

```
vanta/
├── server/
│   ├── ingest/          # Connectors pro Datenquelle
│   ├── processing/      # Schnellfilter, Analyse, Relevanzmodell
│   ├── delivery/        # Zustellplaner, Push
│   ├── monitoring/      # Selbstüberwachung
│   └── db/              # Schema und Migrationen
├── app/                 # iOS-App (Swift / SwiftUI)
├── deploy/              # Docker Compose, Konfiguration
├── docs/                # weiterführende Dokumentation
├── README.md
├── ROADMAP.md
├── CHANGELOG.md
├── SECURITY.md
└── .env.example
```

## Technik (Vorschlag)

| Bereich | Technik |
|---|---|
| Server | Python, FastAPI |
| Datenbank | PostgreSQL mit TimescaleDB und pgvector |
| Sprachmodell | externe API mit Batch-Modus und Prompt Caching |
| App | Swift, SwiftUI, HealthKit, DeviceActivity |
| Push | Apple Push Notification Service |
| Betrieb | Docker Compose, Tailscale |
| Überwachung | Uptime Kuma |

## Einrichtung

Folgt mit Meilenstein M0. Vorgesehen ist:

```bash
git clone <repo-url>
cd vanta
cp .env.example .env      # Zugangsdaten eintragen
docker compose -f deploy/docker-compose.yml up -d
```

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Projektleitfaden, Architektur, Meilensteine |
| [CHANGELOG.md](CHANGELOG.md) | Änderungen pro Version |
| [SECURITY.md](SECURITY.md) | Umgang mit sensiblen Daten und Zugangsdaten |

## Datenschutz

VANTA verarbeitet sehr persönliche Daten, darunter Gesundheitsdaten, Mails und Nutzungsverhalten. Das System ist für den Betrieb auf eigener Hardware und für einen einzelnen Nutzer ausgelegt. Zugangsdaten und echte Daten gehören niemals ins Repository.

## Autor

Jonas Hayk
