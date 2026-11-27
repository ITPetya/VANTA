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

## Installation über SideStore

1. SideStore auf dem iPhone einrichten (siehe Dokumentation von SideStore).
2. `VANTA.ipa` auf das iPhone übertragen (z. B. über die Dateien-App).
3. In SideStore auf "+" tippen und die `.ipa` auswählen. SideStore signiert sie mit der eigenen Apple-ID.
4. SideStore erneuert die Signatur automatisch, bevor sie nach sieben Tagen abläuft (dafür muss SideStore regelmäßig laufen).

Der Build wurde bisher nicht auf einem macOS-Runner ausgeführt; der erste Lauf kann Anpassungen nötig machen.
