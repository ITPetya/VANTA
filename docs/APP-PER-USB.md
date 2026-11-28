# App per USB über den Server installieren

Solange SideStore nicht funktioniert, kann der VANTA-Server die App direkt aufs iPhone bringen: iPhone per Kabel an den Server, ein Befehl (oder ein Tipp auf ein Termius-Snippet), fertig. Kein Windows-PC nötig.

Signiert wird mit einem kostenlosen Apple-Account über [xtool](https://github.com/xtool-org/xtool). Die Signatur gilt wie immer 7 Tage, danach einfach erneut ausführen.

**Status:** noch nicht getestet. Ob die HealthKit-Berechtigung beim Signieren mit xtool erhalten bleibt, zeigt erst der erste Versuch.

## Einmalige Einrichtung

### 1. Eigene Apple-ID zum Signieren (empfohlen)

Die Zugangsdaten liegen danach auf dem Server. Deshalb besser eine **zweite, kostenlose Apple-ID nur zum Signieren** anlegen statt der Haupt-Apple-ID. Die Apple-ID zum Signieren muss nicht die sein, mit der das iPhone angemeldet ist.

### 2. Pakete für die USB-Verbindung

```bash
sudo apt install -y usbmuxd libimobiledevice-utils fuse3
```

### 3. xtool installieren

1. Auf https://github.com/xtool-org/xtool/releases die neueste Datei für Linux mit `x86_64` und `.AppImage` im Namen herunterladen, z. B. per `curl -LO <link>`.
2. Ausführbar machen und in den Pfad legen:

```bash
chmod +x xtool-*.AppImage
sudo mv xtool-*.AppImage /usr/local/bin/xtool
xtool --help
```

### 4. Bei Apple anmelden

```bash
xtool setup
xtool auth
```

Den Anweisungen folgen und mit der Signier-Apple-ID anmelden, inklusive Bestätigungscode. Das SDK (`xtool sdk`) wird für das reine Installieren nicht gebraucht.

### 5. iPhone koppeln

1. iPhone per USB-Kabel an den Server anschließen und entsperren.
2. Bei "Diesem Computer vertrauen?" auf **Vertrauen** tippen und den Gerätecode eingeben.
3. Prüfen:

```bash
idevice_id -l
```

Eine lange Kennung bedeutet: Das iPhone ist erkannt.

### 6. Befehl einrichten

```bash
sudo ln -sf /srv/vanta/deploy/vanta-app-update.sh /usr/local/bin/vanta-app-update
```

## App installieren oder aktualisieren

iPhone anschließen, entsperren, dann:

```bash
vanta-app-update
```

Das lädt die neueste Version aus den GitHub-Releases, signiert sie und installiert sie. Eine bestimmte `.ipa`, z. B. einen Test-Build aus einem Pull Request, gibt man als Pfad mit:

```bash
vanta-app-update /pfad/zu/VANTA.ipa
```

Beim allerersten Mal auf dem iPhone unter Einstellungen > Allgemein > VPN & Geräteverwaltung der Signier-Apple-ID vertrauen.

### Mit einem Tipp aus Termius

In Termius unter **Snippets** ein neues Snippet anlegen, Inhalt `vanta-app-update`, und den VANTA-Host zuordnen. Danach genügt: Kabel einstecken, Snippet antippen.

## Fehlerbehebung

| Meldung | Lösung |
|---|---|
| `Kein iPhone per USB gefunden` | Kabel prüfen (manche Kabel laden nur), iPhone entsperren, Vertrauen bestätigen, `sudo systemctl restart usbmuxd` |
| Anmeldefehler bei Apple | `xtool auth` erneut ausführen |
| Fehler zu Entitlements | Fehlermeldung im Issue festhalten, betrifft vermutlich HealthKit |
