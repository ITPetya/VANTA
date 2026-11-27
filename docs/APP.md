# App bauen und über SideStore installieren

Die App ist ein SwiftUI-Projekt in `app/`. Das Xcode-Projekt wird mit XcodeGen aus `app/project.yml` erzeugt und nicht eingecheckt.

## Lokale Konfiguration

```bash
cp app/Config/VANTA.local.xcconfig.example app/Config/VANTA.local.xcconfig
```

Dort Bundle-ID und Team-ID eintragen. Die Datei ist von Git ignoriert. Ohne sie gelten Platzhalterwerte.

Die Serveradresse steht nicht im Code: Sie wird in der App unter "Einstellungen" eingetragen.

## Build über GitHub Actions

1. Der Workflow liegt in `.github/workflows/app-build.yml` und läuft bei Änderungen in `app/` sowie manuell ("Run workflow").
2. Im Reiter "Actions" den Workflow "App Build" starten (oder auf Änderungen in `app/` warten).
3. Nach dem Lauf das Artefakt `VANTA-ipa` herunterladen und entpacken. Es enthält die unsignierte `VANTA.ipa`.

## Installation und Updates über SideStore

Der PC wird nur einmal gebraucht, für die Einrichtung von SideStore selbst. Danach läuft alles auf dem iPhone.

### Einmalig

1. SideStore auf dem iPhone einrichten (siehe Dokumentation von SideStore).
2. In SideStore unter "Sources" auf "+" tippen und diese Adresse hinzufügen:
   `https://github.com/ITPetya/VANTA/releases/latest/download/source.json`
3. VANTA erscheint in der Quelle. Dort auf "Free" bzw. "Install" tippen.

### Updates

Bei jedem Merge auf `main`, der `app/` betrifft, baut GitHub die App, erhöht die Build-Nummer und veröffentlicht ein Release mit `VANTA.ipa` und `source.json`. SideStore zeigt danach bei VANTA ein Update an, ein Tippen genügt.

SideStore erneuert außerdem die Signatur automatisch im Hintergrund, bevor sie nach sieben Tagen abläuft.

### Hinweise

- Die Adresse `releases/latest/download/...` zeigt immer auf das neueste Release. Spätere Releases für andere Teile von VANTA (z. B. Server) müssen deshalb mit `--latest=false` erstellt werden, sonst findet SideStore die Quelle nicht mehr.
- Die .ipa ist öffentlich herunterladbar. Das ist unkritisch, da sie keine Zugangsdaten enthält. Die Serveradresse wird erst in der App eingetragen.
- Alternativ lässt sich eine .ipa weiterhin manuell installieren: Artefakt `VANTA-ipa` aus dem Workflow-Lauf herunterladen, entpacken und in SideStore über "+" auswählen.

## HealthKit und Entitlements

Die App liest Schlaf, Herzfrequenz, HRV, Ruhepuls, Gewicht und Schritte aus HealthKit (nur Lesezugriff, es wird nichts geschrieben). Neue Werte landen mit eindeutiger ID und Status "nicht hochgeladen" in einem lokalen SwiftData-Zwischenspeicher. Es gibt noch keine Serververbindung. Doppelte Werte werden über die HealthKit-UUID erkannt, der Lesestand (Anchor) wird erst nach dem Speichern weitergesetzt.

Die App ist für einen kostenlosen Apple-Account (Personal Team, Signatur über SideStore) ausgelegt. Datei: `app/VANTA/VANTA.entitlements`.

| Entitlement | Zweck | Kostenloser Account |
|---|---|---|
| `com.apple.developer.healthkit` | HealthKit lesen | verfügbar |
| `com.apple.developer.healthkit.background-delivery` | Hintergrundzustellung neuer Werte | **ungetestet**, siehe unten |

Nicht verwendet (erfordern bezahlten Account): Push Notifications, Family Controls, App Groups, iCloud, Associated Domains.

Nutzungstext: `NSHealthShareUsageDescription` (in `project.yml`). Es ist keine Hintergrundmodus-Angabe (`UIBackgroundModes`) nötig.

### Offener Test über SideStore

Ob HealthKit und besonders die Hintergrundzustellung mit der SideStore-Signatur funktionieren, ist der Zweck dieses Schritts und wurde noch nicht auf einem Gerät geprüft (Build nur über GitHub Actions). Falls die Installation wegen des Eintrags `healthkit.background-delivery` scheitert, diesen Eintrag aus der Entitlements-Datei entfernen. Die App läuft dann weiter, Werte kommen aber nur bei geöffneter App an (die Statusanzeige zeigt dann einen Fehler bei der Hintergrundzustellung).

Hinweis: iOS verrät nicht, ob ein Lesezugriff abgelehnt wurde. Die App erkennt nur "noch nicht angefragt". Bei dauerhaft leeren Werten Zugriff unter Einstellungen > Gesundheit > Datenzugriff prüfen.
