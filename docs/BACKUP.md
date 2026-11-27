# Backup und Wiederherstellung

## Wie das Backup arbeitet

`python -m server.backup run` erzeugt einen Dump der Datenbank (`pg_dump -Fc`), verschlüsselt ihn mit AES-256 (openssl, PBKDF2) und legt ihn als `vanta-<UTC-Zeitstempel>.dump.enc` im Ordner `VANTA_BACKUP_DIR` ab.

- Die Datei wird zuerst als `.part` geschrieben und erst nach vollständigem Erfolg umbenannt. Es entstehen keine halben Backups.
- Erst nach einem erfolgreichen Backup wird die Marker-Datei `VANTA_BACKUP_MARKER_PATH` berührt. Der Status-Endpunkt (`/internal/status`) zeigt daraus das letzte Backup. Schlägt ein Lauf fehl, bleibt der Marker alt und die Stille ist sichtbar.
- Aufbewahrung: nur die neuesten `VANTA_BACKUP_KEEP` Backups (Standard 14) bleiben. Aufgeräumt wird erst nach einem erfolgreichen Backup, ein Fehler löscht nie alte Backups.
- Fehler führen zu Exit-Code 1 und einer Meldung im Log.

## Einrichtung

1. Passphrase erzeugen, außerhalb des Backup-Ordners und getrennt von den Backups sichern (Passwortmanager, zweiter Ort):

   ```bash
   umask 077
   mkdir -p secrets
   openssl rand -base64 48 > secrets/vanta_backup.key
   ```

   **Ohne diese Datei sind die Backups wertlos.** Sie darf nie ins Repository (`*.key` ist in `.gitignore`).
2. In `.env` setzen: `VANTA_BACKUP_DIR`, `VANTA_BACKUP_KEY_PATH`, `VANTA_BACKUP_MARKER_PATH`, optional `VANTA_BACKUP_KEEP`.
3. `pg_dump` (Version wie der Datenbankserver, hier 16) und `openssl` müssen auf dem Rechner vorhanden sein, der das Backup ausführt. Alternativ den Dump aus dem Datenbank-Container holen:

   ```
   VANTA_BACKUP_DUMP_COMMAND=docker compose --env-file .env -f deploy/docker-compose.yml exec -T db pg_dump -Fc -U vanta -d vanta
   ```

   Ist `VANTA_BACKUP_DUMP_COMMAND` leer, verbindet sich `pg_dump` mit den `POSTGRES_`-Einstellungen (Passwort über `PGPASSWORD`, nie auf der Kommandozeile).
4. Täglich per Cron oder systemd-Timer starten, z. B. in der crontab:

   ```
   15 3 * * * cd /pfad/zu/vanta && .venv/bin/python -m server.backup run >> /var/log/vanta-backup.log 2>&1
   ```
5. Zweite Kopie an einem externen Ort (ROADMAP, Abschnitt Backup): den Backup-Ordner verschlüsselt wie er ist an einen anderen Ort kopieren, z. B. per rsync. Die Dateien sind bereits verschlüsselt, die Passphrase gehört nicht dazu.

Zusätzlich sichern: die Schlüsseldateien der Verschlüsselung nach Stufen (siehe VERSCHLUESSELUNG.md). Die Daten der Stufen 2 und 3 sind in der Datenbank schon verschlüsselt, ohne diese Schlüssel aber nach der Wiederherstellung unlesbar.

## Wiederherstellung

Auf einem Rechner mit Docker Compose und `.env`, mit laufender, leerer Datenbank:

1. Neuestes Backup entschlüsseln:

   ```bash
   python -m server.backup decrypt backups/vanta-<Zeitstempel>.dump.enc /tmp/vanta.dump
   ```

   Ohne Python geht es auch direkt:

   ```bash
   openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
     -in backups/vanta-<Zeitstempel>.dump.enc -out /tmp/vanta.dump -pass file:secrets/vanta_backup.key
   ```
2. API stoppen, damit niemand schreibt: `docker compose --env-file .env -f deploy/docker-compose.yml stop api`
3. Dump einspielen (Datenbank vorher leer bzw. neu angelegt):

   ```bash
   docker compose --env-file .env -f deploy/docker-compose.yml exec -T db \
     pg_restore -U vanta -d vanta --clean --if-exists --no-owner < /tmp/vanta.dump
   ```

   Bei TimescaleDB können Meldungen zu Erweiterungen erscheinen. Maßgeblich ist, dass die Prüfung in Schritt 5 stimmt. Bei einer ganz neuen Datenbank vorher `SELECT timescaledb_pre_restore();` und danach `SELECT timescaledb_post_restore();` ausführen (siehe TimescaleDB-Dokumentation).
4. Entschlüsselten Dump löschen: `shred -u /tmp/vanta.dump`
5. Prüfen: API starten, `/internal/status` aufrufen, Zeilenzahlen von `raw_items`, Warteschlange und Quellen mit den Erwartungen vergleichen, einen Wert der Stufe 2 lesen (zeigt, dass die Schlüssel passen).

## Wiederherstellung regelmäßig testen

Ein Backup gilt erst als gültig, wenn die Wiederherstellung funktioniert hat. Mindestens vierteljährlich und nach jeder Änderung am Backup:

1. Auf einer Wegwerf-Datenbank (nicht der produktiven) Schritt 1 bis 5 durchführen.
2. Ergebnis mit Datum festhalten. Die ROADMAP-Aufgabe "Wiederherstellung getestet" erst nach dem ersten echten Test auf dem Mini-PC abhaken.

Die Verschlüsselung und das Entschlüsseln deckt `server/tests/test_backup.py` ab. Der Test mit echter Datenbank und `pg_restore` ist ein manueller Schritt auf dem Server.
