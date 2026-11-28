# Signierte Anfragen und Geräte-Registrierung

Dieses Dokument legt das Format fest, das die App exakt nachbauen muss. Umsetzung auf dem Server: `server/api/signing.py` und `server/api/auth.py`.

## Schlüssel

- Die App erzeugt in der Secure Enclave einen Schlüssel auf der Kurve P-256 (`kSecAttrKeyTypeECSECPrimeRandom`, 256 Bit, `kSecAttrTokenIDSecureEnclave`). Der private Schlüssel verlässt das Gerät nie.
- Der öffentliche Schlüssel wird mit `SecKeyCopyExternalRepresentation` ausgelesen. Das ergibt den unkomprimierten Punkt nach X9.62: 65 Bytes (`0x04 || X || Y`). Er wird als Base64 (Standardalphabet, mit Padding, 88 Zeichen) übertragen.

## Registrierung (einmalig, nur intern)

Die Registrierung läuft nie über die öffentliche Schnittstelle, sondern über Tailscale oder das lokale Netz.

1. Auf dem Server einen Code erzeugen: `python -m server.api.devices_cli create-code` (im Container: `docker compose exec api python -m server.api.devices_cli create-code`). Der Code ist einmalig und standardmäßig 10 Minuten gültig (`VANTA_REGISTRATION_CODE_TTL_SECONDS`). In der Datenbank steht nur sein Hash. Format: vier Gruppen zu je 5 Zeichen, getrennt durch Bindestriche. Groß- und Kleinschreibung und Bindestriche werden ignoriert.
2. Die App sendet an den internen Endpunkt:

```
POST /internal/devices/register
Content-Type: application/json

{"code": "<Code>", "name": "<Gerätename, 1 bis 100 Zeichen>", "public_key": "<Base64, 88 Zeichen>"}
```

Antwort `200`: `{"device_id": <Zahl>}`. Die App speichert die `device_id`. Ungültiger, benutzter oder abgelaufener Code: `403`. Fehlerhafte Eingaben (unbekannte Felder, ungültiger Schlüssel): `422`.

Weitere Befehle: `python -m server.api.devices_cli list` zeigt die Geräte, `python -m server.api.devices_cli revoke <device_id>` sperrt ein Gerät.

## Signierte Anfrage

Jede Anfrage an einen öffentlichen Endpunkt (Pfad `/v1/...`) trägt vier Header:

| Header | Inhalt |
|---|---|
| `X-Vanta-Device` | `device_id` aus der Registrierung, Dezimalzahl |
| `X-Vanta-Timestamp` | Unix-Zeit in ganzen Sekunden (UTC), Dezimalzahl |
| `X-Vanta-Nonce` | 16 Zufallsbytes als 32 Zeichen Kleinbuchstaben-Hex, pro Anfrage neu |
| `X-Vanta-Signature` | Base64 (Standardalphabet) der Signatur |

### Signierte Nachricht

Eine UTF-8-Zeichenkette aus sechs Zeilen, getrennt durch ein einzelnes `\n` (ohne abschließendes `\n`):

```
VANTA-SIG-1
<METHODE in Großbuchstaben>
<Pfad inklusive Query-String, z. B. /v1/ping oder /v1/x?a=1>
<Zeitstempel, exakt wie im Header>
<Nonce, exakt wie im Header>
<SHA-256 des rohen Anfrage-Inhalts als Kleinbuchstaben-Hex>
```

- Pfad und Query-String stehen so, wie sie in der Anfrage gesendet werden (kein erneutes Kodieren).
- Bei Anfragen ohne Inhalt wird der Hash der leeren Eingabe verwendet: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Maximale Größe des Inhalts: 1 MiB.

### Signatur

ECDSA über P-256 mit SHA-256 über die oben beschriebenen Bytes. In Swift: `SecKeyCreateSignature(key, .ecdsaSignatureMessageX962SHA256, message, &error)`. Das Ergebnis ist die DER-kodierte Signatur (ASN.1 `SEQUENCE { r, s }`, höchstens 72 Bytes), die Base64-kodiert in den Header kommt.

## Prüfung auf dem Server

Reihenfolge: Header-Format, Gerät bekannt und nicht gesperrt, Signatur, Zeitstempel, Nonce.

- Zeitstempel: Abweichung von der Serveruhr höchstens `VANTA_AUTH_TOLERANCE_SECONDS` (Standard 60 Sekunden, in beide Richtungen). Die iPhone-Uhr sollte automatisch gestellt sein.
- Nonce: Wird pro Gerät gespeichert, eine zweite Anfrage mit derselben Nonce wird abgelehnt. Gespeichert werden nur Nonces authentischer Anfragen. Nonces, die älter als das doppelte Toleranzfenster sind, werden gelöscht, weil ihr Zeitstempel ohnehin nicht mehr gilt.
- Jede Ablehnung antwortet mit `401` und dem festen Text `unauthorized`, ohne den Grund zu nennen. Der Grund (`bad_signature`, `replayed_nonce`, `timestamp_out_of_range`, `unknown_device`, `device_revoked`, `body_too_large` oder ein Fehler im Header-Format) steht nur im Protokoll (Tabelle `rejected_requests`, mit Methode, Pfad und Zeit, nie mit Inhalt).
- Bei Erfolg wird `last_seen_at` des Geräts aktualisiert.

Wiederholung einer Anfrage nach einem Verbindungsabbruch: neue Nonce und neuer Zeitstempel erzeugen und neu signieren. Die Verarbeitung der Daten selbst bleibt über ihre eindeutige ID idempotent.

## Test der Verbindung

`GET /v1/ping` liefert bei gültiger Signatur `200` mit `{"status": "ok"}`.

## Hinweise für das Gateway

- Der Pfad, den der Server sieht, muss dem signierten Pfad entsprechen. Das Gateway darf Pfad und Query-String nicht umschreiben.
- Das Gateway reicht nur Pfade unter `/v1/` durch. `/internal/` bleibt unerreichbar.
