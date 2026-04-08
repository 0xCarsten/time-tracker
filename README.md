# zeiterfassung

Leichtgewichtige CLI-Zeiterfassung für die Kommandozeile. Speichert Arbeitszeiten lokal in SQLite, trackt Über- und Minusstunden kumulativ und exportiert nach Excel.

---

## Voraussetzungen

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) installiert (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Installation

```bash
git clone <repo-url> zeiterfassung
cd zeiterfassung
uv sync
```

Der Befehl `zeit` ist danach über `uv run zeit` verfügbar.  
Optional global installieren:

```bash
uv tool install .
# danach direkt aufrufbar:
zeit --help
```

## Dateispeicherorte

| Datei | Standard-Pfad |
|---|---|
| Datenbank | `~/.zeiterfassung/zeit.db` (konfigurierbar) |
| Konfiguration | `~/.config/zeiterfassung/config.toml` |
| Excel-Export | Aktuelles Verzeichnis (per `--output` änderbar) |

**DB-Pfad konfigurierbar:** Siehe Abschnitt [Benutzerdefinierte Datenbank](#benutzerdefinierte-datenbank).

---

## Erstkonfiguration

```bash
zeit config --weekly-hours 40.0 --bundesland BY
```

Verfügbare Bundesland-Codes:

| Code | Bundesland | Code | Bundesland |
|---|---|---|---|
| `BB` | Brandenburg | `BE` | Berlin |
| `BW` | Baden-Württemberg | `BY` | Bayern |
| `HB` | Bremen | `HE` | Hessen |
| `HH` | Hamburg | `MV` | Mecklenburg-Vorpommern |
| `NI` | Niedersachsen | `NW` | Nordrhein-Westfalen |
| `RP` | Rheinland-Pfalz | `SH` | Schleswig-Holstein |
| `SL` | Saarland | `SN` | Sachsen |
| `ST` | Sachsen-Anhalt | `TH` | Thüringen |

Tägliches Soll wird automatisch berechnet: `weekly_hours / 5`  
Bei 40h/Woche → **8:00h täglich**.

---

## Benutzerdefinierte Datenbank

Der standardmäßige DB-Pfad ist `~/.zeiterfassung/zeit.db`. Du kannst einen benutzerdefinierten Pfad auf drei Wegen festlegen (nach Priorität):

### 1. CLI-Flag `--db` (höchste Priorität, nur für einen Befehl)

```bash
# Einmalig eine andere Datenbank verwenden
zeit --db /mnt/nas/backup.db saldo
zeit --db ~/Dropbox/arbeitszeiten.db show
zeit --db /tmp/test.db add 2026-04-07 work 09:00-17:00
```

### 2. Umgebungsvariable `ZEIT_DB` (mittlere Priorität)

```bash
# Session-weit andere DB verwenden
export ZEIT_DB=/mnt/nas/arbeitszeiten.db
zeit show
zeit saldo

# Oder ein-einmalig:
ZEIT_DB=/tmp/session.db zeit add 2026-04-07 krank
```

### 3. Config-Datei `--db-path` (niedrigste Priorität, persistent)

```bash
# Dauerhaft speichern in ~/.config/zeiterfassung/config.toml
zeit config --weekly-hours 40.0 --bundesland BY --db-path /mnt/nas/arbeitszeiten.db

# Alle zukünftigen zeit-Befehle nutzen diese DB (außer --db Flag überschreibt)
zeit show      # nutzt /mnt/nas/arbeitszeiten.db
zeit add 2026-04-07 work 09:00-17:00  # nutzt /mnt/nas/arbeitszeiten.db

# Zurück zum Standard (ohne --db-path)
zeit config --weekly-hours 40.0 --bundesland BY
```

**Beispiel: Multi-Projekt-Setup**

```bash
# Projekt A: Datenbank persistent konfigurieren
zeit config --weekly-hours 40.0 --bundesland BY --db-path ~/Projekte/A/arbeitszeiten.db
zeit add 2026-04-07 work 08:00-17:00         # nutzt ~/Projekte/A/arbeitszeiten.db

# Projekt B: Ein-einmalig mit --db überschreiben
zeit --db ~/Projekte/B/arbeitszeiten.db add 2026-04-07 work 08:00-17:00

# Zurück zu Projekt A (aus config.toml)
zeit show
```

---

## Befehle

> **💡 Tipp:** Das Flag `--db` kann vor jedem Befehl verwendet werden, um die Datenbank zu überschreiben:  
> `zeit --db /custom/path.db add 2026-04-07 work 09:00-17:00`

### `zeit add` — Eintrag hinzufügen

```
zeit add DATE_STR ENTRY_TYPE [TIME_RANGE] [--pause FLOAT] [--note TEXT]
```

**Eintragstypen:**

| Typ | Bedeutung | Delta |
|---|---|---|
| `work` | Normaler Arbeitstag | `(Ende - Start - Pause) - Tagessoll` |
| `krank` | Kranktag | `0` (entschuldigt) |
| `urlaub` | Urlaubstag | `0` (entschuldigt) |
| `feiertag` | Feiertag | `0` (entschuldigt, auto-erkannt) |
| `abwesend` | Unentschuldigte Abwesenheit | `-Tagessoll` |

**Beispiele:**

```bash
# Arbeitstag mit 45min Pause
zeit add 2026-04-07 work 08:00-17:00 --pause 0.75

# Arbeitstag ohne Pause (8 Stunden exakt)
zeit add 2026-04-08 work 09:00-17:00

# Überstunden (9.5h - 0.5h Pause = 9h gearbeitet, +1h Überstunde)
zeit add 2026-04-09 work 07:30-17:30 --pause 0.5

# Kranktag
zeit add 2026-04-10 krank

# Urlaubstag mit Notiz
zeit add 2026-04-14 urlaub --note "Osterurlaub"

# Feiertag manuell eintragen
zeit add 2026-04-17 feiertag --note "Karfreitag"

# Abwesend (geht voll auf Minusstunden)
zeit add 2026-04-20 abwesend
```

> **Hinweis:** Bei gesetzlichen Feiertagen im konfigurierten Bundesland wird der Typ automatisch auf `feiertag` gesetzt, auch wenn `work` angegeben wird — außer wenn tatsächlich gearbeitet wurde.

---

### `zeit edit` — Eintrag bearbeiten

```
zeit edit DATE_STR [--type TYPE] [--time HH:MM-HH:MM] [--pause FLOAT] [--note TEXT]
```

Nur die angegebenen Felder werden geändert, der Rest bleibt erhalten.

**Beispiele:**

```bash
# Pause korrigieren
zeit edit 2026-04-07 --pause 1.0

# Arbeitszeit nachträglich anpassen
zeit edit 2026-04-07 --time 08:30-17:00

# Typ ändern (z.B. versehentlich falschen Typ eingetragen)
zeit edit 2026-04-07 --type krank

# Mehrere Felder auf einmal
zeit edit 2026-04-07 --time 09:00-18:00 --pause 0.5 --note "Überstunden genehmigt"
```

---

### `zeit delete` — Eintrag löschen

```
zeit delete DATE_STR
```

Fragt vor dem Löschen zur Bestätigung.

```bash
zeit delete 2026-04-07
# → Delete entry for 2026-04-07? [y/N]:
```

---

### `zeit bulk` — Bulk-Eingabe (interaktiv)

```
zeit bulk
```

Interaktiver Modus: eine Zeile pro Tag, leere Zeile oder `done` zum Beenden.

**Zeilenformat:**

```
YYYY-MM-DD HH:MM-HH:MM [pDEZIMAL]
YYYY-MM-DD krank|urlaub|abwesend|feiertag [NOTIZ]
```

**Beispiel-Session:**

```
$ zeit bulk
Bulk-Eingabe (leere Zeile zum Beenden):
> 2026-04-07 08:00-17:00 p0.75
✓ Gespeichert: work 2026-04-07
> 2026-04-08 09:00-16:30
✓ Gespeichert: work 2026-04-08
> 2026-04-09 krank
✓ Gespeichert: krank 2026-04-09
> 2026-04-10 urlaub Osterurlaub
✓ Gespeichert: urlaub 2026-04-10
> 2026-04-13 abwesend
✓ Gespeichert: abwesend 2026-04-13
>
5 Einträge gespeichert.
```

---

### `zeit saldo` — Überstunden-Saldo

```
zeit saldo [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

Zeigt den kumulierten Überstunden-Saldo. Ohne Parameter: gesamter Zeitraum (erster Eintrag bis heute).

```bash
# Gesamter Saldo
zeit saldo

# Saldo für einen bestimmten Zeitraum
zeit saldo --from 2026-01-01 --to 2026-03-31

# Saldo für April
zeit saldo --from 2026-04-01 --to 2026-04-30
```

**Beispielausgabe:**

```
╭─ Saldo (Overtime Balance) ─╮
│ +02:30                     │
╰────────────────────────────╯
```

---

### `zeit show` — Wochenübersicht

```
zeit show [--week INT] [--month INT]
```

Standard: aktuelle ISO-Woche. Fehlende Werktage werden **rot** hervorgehoben.

```bash
# Aktuelle Woche
zeit show

# Bestimmte KW (ISO-Woche)
zeit show --week 15

# Ganzer Monat
zeit show --month 4
```

**Beispielausgabe:**

```
                           Zeiterfassung
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Date        ┃ Type     ┃ Start ┃ End    ┃ Pause ┃ Delta    ┃ Running Saldo ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ 2026-04-06  │ work     │ 08:00 │ 17:00  │ 00:45 │ +00:15   │ +00:15        │
│ 2026-04-07  │ work     │ 09:00 │ 17:30  │ 00:30 │ +01:00   │ +01:15        │
│ 2026-04-08  │ krank    │       │        │ 00:00 │ +00:00   │ +01:15        │
│ 2026-04-09  │ urlaub   │       │        │ 00:00 │ +00:00   │ +01:15        │
│ 2026-04-10  │ feiertag │       │        │ 00:00 │ +00:00   │ +01:15        │
└─────────────┴──────────┴───────┴────────┴───────┴──────────┴───────────────┘
```

Fehlende Werktage erscheinen rot mit `-08:00` Delta.

---

### `zeit list` — Einträge auflisten

```
zeit list [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

Listet alle Einträge in einem Datumsbereich auf. Fehlende Werktage werden ebenfalls rot angezeigt.

```bash
# Alle Einträge
zeit list

# Bestimmter Zeitraum
zeit list --from 2026-04-01 --to 2026-04-30

# Einzelne Woche
zeit list --from 2026-04-06 --to 2026-04-10
```

---

### `zeit fill-missing` — Fehlende Tage nachpflegen

```
zeit fill-missing [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

Interaktiver Modus, der alle fehlenden Werktage im Zeitraum durchläuft und zur Eingabe auffordert. Enter überspringt einen Tag.

```bash
# Fehlende Tage der letzten Woche nachpflegen
zeit fill-missing --from 2026-03-30 --to 2026-04-03

# Alle bisher fehlenden Tage (ab erstem Eintrag bis heute)
zeit fill-missing
```

**Beispiel-Session:**

```
$ zeit fill-missing --from 2026-04-06 --to 2026-04-08
Fehlende Werktage: 2026-04-06, 2026-04-07, 2026-04-08

2026-04-06 — Eintrag (Enter = überspringen): 08:00-17:00 p0.5
✓ Gespeichert: work 2026-04-06
2026-04-07 — Eintrag (Enter = überspringen): krank
✓ Gespeichert: krank 2026-04-07
2026-04-08 — Eintrag (Enter = überspringen):
⏭  Übersprungen.
```

---

### `zeit export` — Excel-Export

```
zeit export [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--output DATEINAME.xlsx]
```

Exportiert alle Einträge als `.xlsx`-Datei. Standardname: `zeit-export-YYYYMMDD.xlsx` im aktuellen Verzeichnis.

Spalten im Export: `Date`, `Type`, `Start`, `End`, `Pause (h)`, `Delta (h)`, `Running Saldo (h)`

```bash
# Kompletter Export (Standard-Dateiname)
zeit export

# Monatsbericht April
zeit export --from 2026-04-01 --to 2026-04-30

# Jahresbericht mit eigenem Dateinamen
zeit export --from 2026-01-01 --to 2026-12-31 --output jahresbericht-2026.xlsx

# In bestimmtes Verzeichnis
zeit export --from 2026-04-01 --to 2026-04-30 --output ~/Dokumente/april-2026.xlsx
```

---

### `zeit config` — Konfiguration

```
zeit config --weekly-hours FLOAT --bundesland CODE [--db-path PATH]
```

Speichert die Einstellungen in `~/.config/zeiterfassung/config.toml`.  
Das tägliche Soll wird bei jeder Eingabe automatisch aus `weekly_hours / 5` berechnet und **snapshot-weise pro Eintrag gespeichert** — historische Salden bleiben bei Konfigurationsänderungen korrekt.

Optional kann auch der DB-Pfad persistent konfiguriert werden (siehe [Benutzerdefinierte Datenbank](#benutzerdefinierte-datenbank)).

```bash
# 40-Stunden-Woche in Bayern
zeit config --weekly-hours 40.0 --bundesland BY

# 35-Stunden-Woche in NRW
zeit config --weekly-hours 35.0 --bundesland NW

# Teilzeit 30h in Berlin
zeit config --weekly-hours 30.0 --bundesland BE

# Mit benutzerdefinierten DB-Pfad
zeit config --weekly-hours 40.0 --bundesland BY --db-path ~/meine-arbeitszeiten.db
```

---

## Typischer Arbeitsablauf

```bash
# 1. Einmalig einrichten
zeit config --weekly-hours 40.0 --bundesland BY

# 2. Tageseintrag am Feierabend
zeit add 2026-04-07 work 08:00-17:00 --pause 0.75

# 3. Wochenübersicht
zeit show

# 4. Aktuellen Saldo abfragen
zeit saldo

# 5. Vergangene Woche auf einmal nachtragen (Bulk)
zeit bulk

# 6. Monatsexport für Abrechnung
zeit export --from 2026-04-01 --to 2026-04-30 --output april.xlsx
```

---

## Saldo-Logik

| Eintragstyp | Formel | Beispiel (Soll 8:00h) |
|---|---|---|
| `work` | `(Ende - Start - Pause) - Tagessoll` | 9h - 0.5h Pause - 8h = **+0.5h** |
| `krank` | `0` | **±0:00** |
| `urlaub` | `0` | **±0:00** |
| `feiertag` | `0` | **±0:00** |
| `abwesend` | `-Tagessoll` | **-8:00** |
| Fehlender Werktag | `-Tagessoll` | **-8:00** (rot markiert) |

Der Saldo wird **kumulativ** über alle Einträge berechnet. Das tägliche Soll wird zum Zeitpunkt der Eingabe gespeichert — nachträgliche Konfigurationsänderungen verändern historische Einträge nicht.

---

## Entwicklung

```bash
# Install for development
 uv tool install . -e
```
```bash
# Tests ausführen
uv run pytest

# Mit Coverage
uv run pytest --cov=zeiterfassung --cov-report=term-missing

# Einzelne Testdatei
uv run pytest tests/domain/test_rules.py -v
```

**Projektstruktur:**

```
zeiterfassung/
├── zeiterfassung/
│   ├── cli/           # Typer-Commands, Rich-Formatter
│   ├── domain/        # Reine Logik (I/O-frei): Modelle, Regeln, Feiertage
│   ├── repository/    # SQLite-Zugriff
│   ├── services/      # Orchestrierung: EntryService, SaldoService, ExportService
│   └── config.py      # Einstellungen lesen/schreiben (TOML)
├── tests/             # pytest, >94% Coverage in domain/ und services/
└── pyproject.toml     # uv-Abhängigkeiten, `zeit` als Script-Einstieg
```
