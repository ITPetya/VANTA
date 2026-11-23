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

## Betrieb

- Server nur über Tailscale erreichbar, keine offenen Ports ins Internet
- Datenbank nicht direkt erreichbar, nur über den Server
- Tägliches verschlüsseltes Backup, zweite Kopie extern, Wiederherstellung regelmäßig testen
- Abhängigkeiten regelmäßig aktualisieren

## Sprachmodell und manipulierte Inhalte

Mails und Artikel können Anweisungen enthalten, die das Sprachmodell zu ungewollten Aktionen bringen sollen (Prompt Injection). Deshalb:

- Eingehende Inhalte werden als Daten behandelt, nie als Anweisungen.
- VANTA hat keine Aktionen mit Außenwirkung (Senden, Löschen, Antworten) ohne Bestätigung durch den Nutzer.
- Jede Aktion der KI wird protokolliert.
