# Server einrichten

Schritt für Schritt vom leeren Mini-PC (z. B. Lenovo ThinkCentre M720q) bis zum laufenden VANTA-Server mit Backup.

Platzhalter in spitzen Klammern ersetzen, z. B. `<server-ip>`.

**Zeitbedarf:** etwa 1,5 bis 2 Stunden.

**Du brauchst:** USB-Stick (mindestens 4 GB, wird gelöscht), Bildschirm und Tastatur nur für die Installation, Netzwerkkabel, einen PC mit SSH (Windows: PowerShell oder Termius).

---

## Teil 1: Installation

### 1. Installationsstick erstellen

1. Auf https://www.debian.org die aktuelle **Debian 13 "netinst"**-ISO für **amd64** herunterladen.
2. Unter Windows mit **Rufus** (https://rufus.ie) auf den USB-Stick schreiben. Standardeinstellungen passen.

### 2. BIOS einstellen

Mini-PC anschalten und sofort mehrfach **F1** drücken (Lenovo).

- **Power > After Power Loss:** `Power On`. Nach einem Stromausfall startet der Server dann von selbst.
- Optional, spart Strom: WLAN, Bluetooth und Audio deaktivieren, falls die Optionen vorhanden sind.
- Mit **F10** speichern und neu starten.

### 3. Debian installieren

USB-Stick einstecken, beim Start **F12** drücken und den Stick als Startmedium wählen.

| Abfrage | Eingabe |
|---|---|
| Installationsart | **Install** (die Textvariante) |
| Sprache, Land, Tastatur | Deutsch, Deutschland, Deutsch |
| Rechnername | `vanta` |
| Domain | leer lassen |
| Root-Passwort | **leer lassen**. Dann bekommt dein Benutzer automatisch `sudo`-Rechte. |
| Benutzer | dein Name, z. B. `jonas`, mit starkem Passwort |
| Partitionierung | **Geführt, vollständige Festplatte verwenden**, dann **Alle Dateien auf eine Partition** |
| Paketmanager-Spiegel | Deutschland, `deb.debian.org` |
| Softwareauswahl | **nur** `SSH server` und `Standard-Systemwerkzeuge`. Alle Desktop-Einträge abwählen. |
| GRUB | Ja, auf die interne SSD |

Nach dem Neustart Stick abziehen, anmelden und die IP-Adresse notieren:

```bash
ip -br a
```

Ab hier geht alles vom PC aus per SSH. Bildschirm und Tastatur werden nicht mehr gebraucht.

```bash
ssh <benutzer>@<server-ip>
```

---

## Teil 2: Grundeinrichtung

### 4. System aktualisieren und Werkzeuge installieren

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl ca-certificates unattended-upgrades powertop python3-venv openssl ufw
```

Automatische Sicherheitsupdates einschalten (im Dialog **Ja** wählen):

```bash
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 5. Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Den angezeigten Link öffnen und den Server deinem Tailnet hinzufügen. Danach erreichst du ihn über seinen Tailscale-Namen (z. B. `vanta`) oder die Tailscale-IP (`tailscale ip -4`), egal wo du bist.

In der Tailscale-Verwaltung beim Gerät **"Disable key expiry"** aktivieren, sonst fliegt der Server nach einigen Monaten aus dem Tailnet.

### 6. SSH nur noch mit Schlüssel

**Auf dem PC** (PowerShell) einen Schlüssel erzeugen, falls noch keiner existiert, und auf den Server kopieren:

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <benutzer>@<server-ip> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

In Termius: unter Keychain einen Schlüssel erzeugen und über "Export to host" auf den Server übertragen.

**Neues SSH-Fenster öffnen und prüfen, dass die Anmeldung ohne Passwort klappt.** Erst dann auf dem Server den Passwort-Login abschalten:

```bash
sudo tee /etc/ssh/sshd_config.d/10-vanta.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sudo systemctl reload ssh
```

### 7. Firewall

Eingehend nur SSH aus dem Heimnetz und alles über Tailscale. `<heimnetz>` ist z. B. `192.168.178.0/24` (FRITZ!Box) oder `192.168.0.0/24`, siehe Ausgabe von `ip -br a`.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <heimnetz> to any port 22 proto tcp
sudo ufw allow in on tailscale0
sudo ufw enable
sudo ufw status verbose
```

Die API von VANTA lauscht nur auf `127.0.0.1`, die Datenbank ist gar nicht nach außen veröffentlicht. Beides ist dadurch zusätzlich geschützt.

Hinweis: Die Sperre der Verbindungen **vom** Server **ins** Heimnetz (SECURITY.md, Regel 7) folgt zusammen mit der öffentlichen Schnittstelle in M1, am besten über ein eigenes VLAN im Router.

### 8. Stromsparen und Logs begrenzen

Stromsparoptionen bei jedem Start aktivieren:

```bash
sudo tee /etc/systemd/system/powertop.service >/dev/null <<'EOF'
[Unit]
Description=Powertop auto-tune

[Service]
Type=oneshot
ExecStart=/usr/sbin/powertop --auto-tune

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now powertop.service
```

Systemprotokoll auf 500 MB begrenzen:

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=500M\n' | sudo tee /etc/systemd/journald.conf.d/size.conf
sudo systemctl restart systemd-journald
```

---

## Teil 3: Docker

### 9. Docker installieren

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Logs der Container begrenzen:

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

**Einmal ab- und wieder anmelden**, damit die Docker-Gruppe gilt. Test: `docker run --rm hello-world`.

---

## Teil 4: VANTA

### 10. Repository holen

```bash
sudo mkdir -p /srv/vanta
sudo chown $USER: /srv/vanta
git clone https://github.com/ITPetya/VANTA.git /srv/vanta
cd /srv/vanta
```

### 11. Schlüssel erzeugen

```bash
umask 077
mkdir -p secrets backups
echo "1:$(openssl rand -base64 32)" > secrets/vanta_level2.key
echo "1:$(openssl rand -base64 32)" > secrets/vanta_level3.key
openssl rand -base64 48 > secrets/vanta_backup.key
# Die Schlüssel der Stufen 2 und 3 liest der Container (Benutzer-ID 10001):
sudo chown 10001:10001 secrets/vanta_level2.key secrets/vanta_level3.key
sudo chmod 400 secrets/vanta_level2.key secrets/vanta_level3.key
```

**Sofort sichern:** alle drei Dateien zusätzlich an einem zweiten Ort ablegen, z. B. im Passwortmanager (Inhalt anzeigen mit `sudo cat secrets/<datei>`). Ohne sie sind verschlüsselte Daten und Backups unwiederbringlich verloren.

### 12. Konfiguration

```bash
cp .env.example .env
chmod 600 .env
openssl rand -base64 32 | tr -d '/+=' ; echo
nano .env
```

In der `.env` eintragen bzw. ändern:

```
POSTGRES_PASSWORD=<die eben erzeugte Zeichenfolge>

VANTA_BACKUP_DIR=/srv/vanta/backups
VANTA_BACKUP_KEY_PATH=/srv/vanta/secrets/vanta_backup.key
VANTA_BACKUP_MARKER_PATH=/srv/vanta/backups/last_backup
VANTA_BACKUP_DUMP_COMMAND=docker compose --env-file /srv/vanta/.env -f /srv/vanta/deploy/docker-compose.yml exec -T db pg_dump -Fc -U vanta -d vanta
```

`VANTA_TEST_DATABASE_URL` **leer lassen**. Speichern mit Strg+O, Enter, beenden mit Strg+X.

### 13. Starten

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

Beim ersten Start wird das Datenbank-Image geladen (über 1 GB, dauert einige Minuten). Der Dienst `migrate` legt die Tabellen an und beendet sich danach, das ist richtig so.

Prüfen:

```bash
curl -s http://127.0.0.1:8000/internal/health
curl -s http://127.0.0.1:8000/internal/status
```

Erwartet: `{"status":"ok"}` und eine Statusübersicht.

Bei Problemen die Logs ansehen:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml logs --tail 50 migrate api db
```

---

## Teil 5: Backup und Überwachung

### 14. Backup einrichten

```bash
cd /srv/vanta
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/python -m server.backup run
ls -l backups/
```

Es sollte eine Datei `vanta-<Zeitstempel>.dump.enc` und die Datei `last_backup` entstehen. Danach täglich um 03:15 automatisch:

```bash
crontab -e
```

Diese Zeile anhängen:

```
15 3 * * * cd /srv/vanta && .venv/bin/python -m server.backup run >> /srv/vanta/backups/backup.log 2>&1
```

**Zweite Kopie:** den Ordner `/srv/vanta/backups` regelmäßig auf ein anderes Gerät kopieren (z. B. einen Rechner im Rack per `rsync` über Tailscale). Die Backups sind bereits verschlüsselt, die Datei `vanta_backup.key` gehört **nicht** dazu.

### 15. Wiederherstellung testen

Pflicht für den Abschluss von M0: einmal nach [BACKUP.md](BACKUP.md), Abschnitt "Wiederherstellung regelmäßig testen", ein Backup in eine Wegwerf-Datenbank einspielen. Erst danach in der ROADMAP "Wiederherstellung getestet" abhaken.

### 16. Uptime Kuma

Die API ist nur lokal auf dem Server erreichbar. Deshalb meldet der Server sich selbst bei Uptime Kuma:

1. In Uptime Kuma einen Monitor vom Typ **Push** anlegen, Intervall 5 Minuten, Push-URL kopieren.
2. Auf dem Server `crontab -e` und anhängen:

```
*/5 * * * * curl -fsS -m 10 http://127.0.0.1:8000/internal/health >/dev/null && curl -fsS -m 10 "<kuma-push-url>" >/dev/null
```

Ist VANTA nicht gesund oder der Server aus, bleibt der Push aus und Uptime Kuma schlägt Alarm.

---

## Teil 6: Betrieb

### VANTA aktualisieren

```bash
cd /srv/vanta
git pull
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

Neue Migrationen laufen dabei automatisch.

### Nützliche Befehle

| Zweck | Befehl |
|---|---|
| Status der Container | `docker compose --env-file .env -f deploy/docker-compose.yml ps` |
| Logs | `docker compose --env-file .env -f deploy/docker-compose.yml logs -f api` |
| Neustart | `docker compose --env-file .env -f deploy/docker-compose.yml restart` |
| Stoppen | `docker compose --env-file .env -f deploy/docker-compose.yml down` (Daten bleiben erhalten) |
| Speicherplatz | `df -h` und `docker system df` |
| RAM (Wert "available" zählt) | `free -h` |

**Niemals** `docker compose down -v` ausführen: `-v` löscht die Datenbank.

### Abschluss-Checkliste

- [ ] Server startet nach Stromausfall von selbst
- [ ] SSH nur mit Schlüssel, über Tailscale erreichbar
- [ ] Firewall aktiv
- [ ] `/internal/health` liefert `ok`
- [ ] Schlüssel an einem zweiten Ort gesichert
- [ ] Backup läuft täglich, zweite Kopie eingerichtet
- [ ] Wiederherstellung einmal getestet
- [ ] Uptime Kuma meldet den Server als online
