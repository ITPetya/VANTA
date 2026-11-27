# Verschlüsselung und Schlüssel

VANTA verschlüsselt nach Sensibilitätsstufen (siehe SECURITY.md):

| Stufe | Behandlung |
|---|---|
| 1 | unverschlüsselt |
| 2 | AES-256-GCM, eigener Schlüssel |
| 3 | AES-256-GCM, anderer eigener Schlüssel |

Die Schlüssel liegen in Dateien außerhalb des Repositorys. In `.env` stehen nur die Pfade (`VANTA_KEY_LEVEL2_PATH`, `VANTA_KEY_LEVEL3_PATH`). Fehlt ein Pfad oder eine Datei, bricht der Server beim Verschlüsseln mit einer klaren Fehlermeldung ab, er schreibt nie unverschlüsselt.

## Schlüssel erzeugen

Zwei verschiedene Schlüssel, einer pro Stufe. Format pro Zeile: `<Version>:<Base64 von 32 Zufallsbytes>`.

```bash
umask 077
mkdir -p secrets
echo "1:$(openssl rand -base64 32)" > secrets/vanta_level2.key
echo "1:$(openssl rand -base64 32)" > secrets/vanta_level3.key
```

Danach in `.env` die Pfade eintragen (im Container z. B. `/run/secrets/vanta_level2.key`). Die Dateien nie einchecken (`*.key` ist in `.gitignore`).

**Wichtig:** Ohne Schlüssel sind die Daten unwiederbringlich verloren. Beide Dateien getrennt von den Datenbank-Backups sichern.

## Schlüsselrotation

Neue Zeile mit höherer Version an die Datei anhängen, z. B. `2:<neuer Schlüssel>`. Neue Daten werden mit der höchsten Version verschlüsselt, ältere Daten bleiben mit ihrer gespeicherten Version lesbar. Alte Zeilen erst entfernen, wenn keine Daten mehr damit verschlüsselt sind.

## Technische Hinweise

- Jeder Wert enthält Schlüsselversion, Nonce und Ciphertext samt Prüfsumme.
- Der Datenschlüssel wird pro Nutzer aus dem Hauptschlüssel abgeleitet (HKDF), Nutzer-ID und Stufe sind an den Ciphertext gebunden. Daten eines Nutzers lassen sich nicht als Daten eines anderen entschlüsseln.
- Eigene Schlüsseldateien pro Nutzer (ROADMAP, Abschnitt 13) erfordern nur einen anderen `KeyProvider` in `server/crypto.py`.
