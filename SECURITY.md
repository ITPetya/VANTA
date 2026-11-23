# Sicherheit

VANTA verarbeitet Gesundheitsdaten, Mails, Termine und Nutzungsverhalten. Diese Regeln gelten für Entwicklung und Betrieb.

## Niemals ins Repository

- Zugangsdaten, API-Schlüssel, Passwörter, Tokens
- Die Datei `.env` (nur `.env.example` ohne echte Werte wird eingecheckt)
- Schlüssel für Verschlüsselung und Apple Push (`*.p8`, `*.pem`, `*.key`)
- Echte Daten, Datenbank-Dumps, Backups, Logs mit Inhalten
- Exporte aus HealthKit, Mailpostfächern oder Kalendern

Wurde trotzdem etwas eingecheckt: den betroffenen Schlüssel sofort widerrufen und neu erzeugen. Ein Entfernen aus der Git-Historie allein reicht nicht.

## Sensibilitätsstufen

| Stufe | Daten | Regel |
|---|---|---|
| 1 | Nachrichten, Trends | normal speichern, externe API erlaubt |
| 2 | Mails, Termine, Nutzungsverhalten | verschlüsselt speichern, Schlüssel getrennt, externe API erlaubt |
| 3 | Gesundheitsdaten | verschlüsselt und separat speichern, nur lokal verarbeiten |

## Verbindung zwischen App und Server

Ziel: Über die öffentliche Schnittstelle fließen ausschließlich definierte Daten zwischen App und Server. Niemand bekommt darüber Zugriff auf den Server oder auf das Heimnetz.

### Aufbau

```
iPhone-App  ->  Cloudflare Tunnel  ->  Gateway-Container  ->  API-Container  ->  Datenbank
                (kein offener Port     (Allowlist,            (Schema-Prüfung,    (nur intern
                 zu Hause)              Größenlimit,           Geräteprüfung)      erreichbar)
                                        Rate-Limit)
```

### Regeln

1. **Kein offener Port.** Der Server baut die Verbindung zu Cloudflare selbst nach außen auf. Im Router wird nichts freigegeben.
2. **Allowlist.** Nur fest definierte Endpunkte existieren öffentlich. Alles andere wird verworfen. Es gibt öffentlich keine Verwaltungs-, Datei- oder Debug-Endpunkte.
3. **Geräte-Authentifizierung.** Die App erzeugt einen Schlüssel in der Secure Enclave des iPhones, der das Gerät nie verlässt. Jede Anfrage wird damit signiert, inklusive Zeitstempel gegen Wiederholung. Das Gerät wird einmalig über Tailscale bzw. das lokale Netz registriert, nie über die öffentliche Schnittstelle.
4. **Strenge Schemas auf beiden Seiten.** Jeder Endpunkt hat ein festes Format mit Typen, Wertebereichen und Maximallängen. Unbekannte Felder führen zur Ablehnung. Die App prüft Antworten des Servers genauso.
5. **Dateien nach Inhalt prüfen, nie nach Endung.** Erlaubte Dateien werden neu kodiert, dadurch entfallen Metadaten, Kommentare und versteckte Inhalte.
6. **Abgeschottete Container.** Gateway und API laufen in eigenen Docker-Netzen. Die Datenbank ist nur aus dem internen Netz erreichbar.
7. **Kein Weg ins Heimnetz.** Der VANTA-Server steht in einem eigenen Netzsegment (VLAN), oder die Host-Firewall sperrt alle Verbindungen ins Heimnetz. Erlaubt sind nur ausgehende Verbindungen zu den benötigten Diensten (LLM-API, Mail, Nachrichtenquellen, Cloudflare).
8. **Alles Abgelehnte wird protokolliert** und erscheint im Status der App.

## Betrieb

- Server: eigener Rechner nur für VANTA, Debian minimal, Docker Compose
- Verwaltung (SSH, Datenbank) ausschließlich über Tailscale
- SSH nur mit Schlüssel, Passwort-Login deaktiviert
- Automatische Sicherheitsupdates
- Tägliches verschlüsseltes Backup, zweite Kopie extern, Wiederherstellung regelmäßig testen
- Abhängigkeiten regelmäßig aktualisieren

## Repository

- GitHub Secret Scanning mit Push Protection ist aktiviert
- Lokaler Pre-Commit-Check auf Schlüssel (z. B. gitleaks)
- Private Konfiguration liegt in `config/` (ignoriert), Vorlagen in `config.example/`
- Team-ID und Bundle-ID der App stehen in einer lokalen, ignorierten `.xcconfig`
- Secrets für GitHub Actions nur über die verschlüsselten Repository-Secrets

## Sprachmodell und manipulierte Inhalte

Mails und Artikel können Anweisungen enthalten, die das Sprachmodell zu ungewollten Aktionen bringen sollen (Prompt Injection). Deshalb:

- Eingehende Inhalte werden als Daten behandelt, nie als Anweisungen.
- VANTA hat keine Aktionen mit Außenwirkung (Senden, Löschen, Antworten) ohne Bestätigung durch den Nutzer.
- Jede Aktion der KI wird protokolliert.
