# Jahreszeit-Varianten der Airport-Szenerien (Stand 2026-10-24)

> **Vorläufig.** Die Scans liefen per Subagent und sind bis auf die Zeilen mit `verified = ja` nicht einzeln nachgeprüft. Im Sim ist nichts getestet. Die Faktentabelle steht in `docs/plans/airport-seasons.tsv` (Issue #24).

## 1. Ziel und Umfang

Welche Airport-Szenerie lässt sich auf eine andere Jahreszeit umschalten, und wie genau. Rein lesend: nichts umgeschaltet, nichts umbenannt, `scenery_packs.ini` unberührt. Archive nur mit `7z l` gelistet.

| Stufe | Umfang |
|---|---|
| Stufe 1 | 535 verlinkte Packs aus `~/X-Plane-12/Custom Scenery/` (Ziel unter `/mnt/xplane_data/Scenery/`), vier Teile |
| Stufe 2 | 1636 nicht verlinkte Packs unter `/mnt/xplane_data/Scenery/` |
| Lückenlauf | die 535 verlinkten Packs noch einmal mit den drei Mustern, die Stufe 1 übersehen hatte (siehe 7) |
| Review | Codex-Review mit Nachprüfung am 2026-10-24, siehe 10 |

Ergebnis: 108 Zeilen (A, B, C, D) in der TSV. Reine E-Zeilen („nichts gefunden“) stehen nicht darin, es sind 391.

Acht Packs unter `/mnt/xplane_data/Scenery/` standen in keiner der beiden Listen (darunter `XCodr/AEP1-4`, das Ziel-Pack `GlobalArt/CA-CYYZ-A-Toronto Airport Pearson-NLMod`, `Flightbeam Library`, `Zambesi_Library`). Nur `AEP1-4` hat Jahreszeit-Marker; es steht als B in der TSV.

## 2. Kategorien

| Kat. | Bedeutung | Was man tun muss |
|---|---|---|
| A | umschaltbar, Dateien vorhanden | Dateien/Ordner tauschen oder Pack wechseln (von Hand) |
| B | nativ, automatisch (X-Plane 12 `EXPORT_*SEASON`, `SEASONAL` in `.for`) | nichts; folgt Simulatordatum und Breitengrad |
| C | Plugin-gesteuert (Dataref `sam/season/*`, `maxxxp/seasonsxp/*`, `nm/four_seasons/season`) | Plugin-Einstellung; nur wenn das Plugin installiert ist |
| D | behauptet oder deklariert, aber Dateien fehlen | nichts zu schalten |
| E | nichts gefunden | nichts |

## 3. Installierte Plugins

In `~/X-Plane-12/Resources/plugins`:

| Plugin | Stand | Folge |
|---|---|---|
| SAM 3.1.10 | **deaktiviert**: in `SAM/{lin,mac,win}_x64/` liegt nur `SAM.xpl.xorg` (und `.xorgbak`), kein `SAM.xpl`; `Log.txt` vom 2026-10-24 lädt nur openSAM | würde `sam/season/{spring,summer,autumn,winter,deepwinter,snowytrees}` setzen (Strings der `.xorg`-Datei), Menü „Colors + Seasons“. Hier setzt niemand `deepwinter` oder `snowytrees` |
| openSAM | installiert und geladen (`Log.txt`), `Output/openSAM/preferences.xml`: `<seasons auto_season="1" …>` | einziger aktiver Lieferant der `sam/season/*`-Datarefs; setzt nur `sam/season/{spring,summer,autumn,winter}` (Menü „SAM legacy Season: Auto/Spring/…“), Auto = nach Datum. `deepwinter` und `snowytrees` fehlen in den Strings |
| XA-snow | installiert (`Output/preferences/OrthoSnow.cfg`) | dynamischer Schnee über Ortho/Boden, unabhängig von den Packs |
| TerraMaxx SeasonsXP | **nicht installiert** | `maxxxp/seasonsxp/*` wird nie gesetzt, es gilt nur die `default`-Region (Sommer) |
| 4 Seasons | **nicht installiert** | `nm/four_seasons/season` wird nie gesetzt |

Bei C-Zeilen mit SAM/openSAM gilt: die Library-Regionen reagieren auf das Dataref. Weil SAM deaktiviert ist, wirken hier nur die vier openSAM-Jahreszeiten. Ob das openSAM-Menü im laufenden Sim umschaltet, ist nicht geprüft.

## 4. A: umschaltbar mit vorhandenen Dateien

Alle Wege sind manuell. Vorher Sicherung anlegen. Dokumentiert vom Vendor ist nur Oulu (Readme); die übrigen Tauschwege sind aus der Dateistruktur abgeleitet.

| Szenerie | ICAO | Umschalten | Zurück | verifiziert |
|---|---|---|---|---|
| Ibertech LOWG Graz | LOWG | `Seasons/winter/library.txt` über die `library.txt` im Pack-Wurzelordner kopieren; Default-Region zeigt dann auf `orthos/neutral_winter/…` | `Seasons/summer/library.txt` zurückkopieren (byte-gleich mit dem Original); Vegetation bleibt auch im Winter Sommer | ja |
| GlobalArt Pearson Winter Texture | CYYZ | `images/` und `textures/` des Add-ons über das Pack `CA-CYYZ-A-Toronto Airport Pearson-NLMod` kopieren (431 von 450 Dateien unterscheiden sich) | `images/`: `Backup Texturas Verao/images/` zurückkopieren (gleich dem installierten Stand). `textures/`: vorher die Pack-eigenen `textures/` sichern und daraus zurückholen; das Backup heißt `Textures/` (großes T, 382 Dateien) und weicht bei 31 der 88 überschriebenen Dateien vom installierten NLMod-Pack ab | ja |
| Kumiankka Oulu VFR | EFOU (Gebiet) | Paket `OuluVFR_winter_v2.4.0` statt `OuluVFR_summer_v2.4.0` verwenden. Das Readme sagt: eines von beiden kopieren. Der Winter unterscheidet sich nur in DSF, `apt.dat` und Weihnachtsbaum-Texturen. Schnee kommt vom externen Plugin Accumulated Snow | Eintrag in `scenery_packs.ini` zurück auf das Sommer-Paket (Betreiber) | ja |
| Ibertech EKCH Airport 1 | EKCH | Ordner `autumn/` (36 Dateien: `grass/*.for`, `objects/{ekch_hills,ekch_trees,ground,ground_ov}/*.obj`) über die gleichnamigen Dateien im Pack-Wurzelordner kopieren; die DSF verweist auf die Wurzelpfade | die 36 Wurzeldateien vorher sichern, es gibt kein Backup im Pack | nein |
| x-flight UIAR Chara (Forest) | UIAR | `forest/winter/TARA_trees.png` über `forest/TARA_trees.png` kopieren (alle `1TARA-*.for` referenzieren sie) | Original vorher sichern | nein |
| Skyline KSNA John Wayne | KSNA | schwach: `Ground/grass2.png` über `Ground/grass2_winter.png` (die DSF nutzt `grass_winter_KSNA_Skyline*.obj` mit `grass2_winter.png`); nicht getestet; gleiche Dateien im „- Patch“-Pack | `grass2_winter.png` vorher sichern | nein |

Die Tabelle zeigt sieben Packs. Die TSV hat acht A-Zeilen, weil Oulu drei Zeilen hat (Winter-Pack mit Variante `winter` und `summer`, dazu das nicht verlinkte Sommer-Pack).

EKCH hat zwei unabhängige Wege: Ibertech (A, oben) und FlyTampa (C, unten).

## 5. C: Plugin-gesteuert

| Szenerie | ICAO | Mechanismus | Stand hier |
|---|---|---|---|
| FlyTampa Copenhagen (Airport, City, Overlays, Photoreal, Mesh) | EKCH | `FlyTampa_EKCH_XP_SeasonPack.7z` (1,8 GB, nicht entpackt, enthält fünf `library.txt` plus `autumn/winter/deepwinter`-Ordner) ersetzt die `library.txt` der Packs. Regionen `sam/season/*` oder `nm/four_seasons/season` | installierte `library.txt` ohne Season-Regionen, die Ordner `summer/autumn/winter/deepwinter` liegen schon im Pack. Ohne das Archiv inaktiv (verifiziert). Mit Archiv: openSAM schaltet Frühling bis Winter; `deepwinter`/`snowytrees` bräuchten SAM (deaktiviert) oder 4 Seasons (fehlt) |
| Axonos Jackson Hole | KJAC | `REGION_DREF sam/season/*` in der `library.txt` (Pack-Wurzelordner); im Winter Tausch auf `Snowalt/*_Snow.obj` (56 Dateien) | openSAM (Frühling bis Winter), Szenerie neu laden. `deepwinter`/`snowytrees` nur mit SAM, das hier deaktiviert ist (verifiziert) |
| Axonos Varna | LBWN | wie KJAC, nur Vegetation | openSAM (SAM deaktiviert) |
| XorgBig Devinci Kobe | RJBE | wie KJAC, nur Vegetation | openSAM (SAM deaktiviert) |
| SFD Salt Lake City | KSLC | `sam/season/*` oder `maxxxp/seasonsxp/*` | openSAM für Herbst/Winter, `deepwinter` nicht (SAM deaktiviert); SeasonsXP fehlt |
| CFXP Vancouver (+ `.patch-xp12`) | CYVR | `sam/season/{spring,autumn,winter,deepwinter}`, alle 107 Ziele je Region vorhanden | SAM/openSAM |
| CFXP Vancouver City | CYVR (City) | wie CYVR, teilweise | SAM/openSAM |
| FlyAgi_Vegetation | – | `sam/season/*` und `sam/color/*`, 817 von 821 Zielen je Region | SAM/openSAM |
| Ibertech Bremen | EDDW | `maxxxp/seasonsxp/is_*` | SeasonsXP fehlt, nur Sommer. Ziele der Winter-Regionen fehlen (siehe D) |
| Ibertech Graz | LOWG | `maxxxp/seasonsxp/is_*` | SeasonsXP fehlt (zusätzlich A, siehe oben) |

## 6. D: behauptet oder deklariert, Dateien fehlen

| Szenerie | ICAO | Was fehlt |
|---|---|---|
| Axonos Memphis | KMEM | `sam/season`-Regionen deklariert, 487 von 487 Sommer-Zielen fehlen, kein `SAM_Seasons_SDK` |
| CFSS Alaska | CYAZ | Regionen `sam/season/*` ohne `EXPORT`-Zeilen |
| CFXP Kelowna | CYLW | fünf Regionen `sam/season/*` definiert, aber nie mit `REGION` benutzt (nur `REGION CYLW`) |
| GlobalArt Vancouver | CYVR | Handbuch (EN/PT) nennt „Winter texture - only the Airport area“, keine Dateien |
| Ibertech Berlin | EDDB | `sam/season/*` mit etwa 840 Zeilen je Region, `SAM_Seasons_SDK` fehlt |
| Ibertech Bremen | EDDW | Winter/Mid-Winter-Ziele in `library.txt` verdrahtet, Dateien fehlen (0 von 1187) |
| Ibertech Tromsø | ENTC | `O4XP_Seasons.py` erzeugt eine Season-Library aus `terrain/` und `textures/`; Voraussetzungen fehlen |
| Ibertech Sion | LSGS | `terrain invierno.zip` (Winter-Ortho): Namen passen nicht zu den DSF-Polygonen, nicht einfach nutzbar; `Snow/` nicht referenziert |
| NorthernSky Kotzebue | PAKT | Changelog nennt Seasons, nichts im Pack |
| Papickx Airport Environment HD | – | `maxxxp/seasonsxp/is_winter`-Region definiert, nie verwendet; SeasonsXP fehlt |
| x-flight Kurumoch | UWWW | `phototerr/winter/*.png` vorhanden, die DSF verweist nicht auf die `.pol` |
| XCodr Yellowstone | KWYS | Winter-`EXPORT_EXCLUDE`-Block in `Library Contents.txt`, aber `Ortho/Winter/*.pol` fehlt |
| XorgBig Joensuu | EFJO | altes Readme behauptet Sommer-/Winter-Boden, nur DSF und Objekte im Pack |
| ZeroDollar zdp-library 1.2.0 | – | `#NO ASSETS DEFINED` in den Winterregionen |
| ZeroDollar zdp-library (`old/`) | – | wie 1.2.0, gleicher Regionsaufbau |

## 7. B: nativ und automatisch (nichts zu schalten)

Nur Simulatordatum und Breitengrad zählen. 58 Packs, Zeilen in der TSV.

- **`EXPORT_EXCLUDE_SEASON` im Pack-Wurzel-`library.txt`:** FlyAgi (EDDK, EDPW, EDRN, EDXE, LOWI, EDNL, UGAM, LKCM), Simmershome (EDAB, EDAQ, EDAU, EDAY, EDAZ, EDOP, ETNL) und XCodr `AEP1-4` (ältere AEP-Library, nicht verlinkt). EDAB, EDAZ und ETNL haben tote Winterziele.
- **`EXPORT_SEASON` und Verwandte:** XCodr (AEP, A30, KBLU), ChudobaDesign (Library, ESGG), FSX3D LFKB, Orbx `Global_Forests_v2`.
- **`SEASONAL` in `.for`:** PH20 (EBBL, EHEH, EHRD, EKAH), Military EBFS, Colombia 1.3 (10 Packs, nur `_sp`), Colombia 1.4 `L_XPC_LuiMor_free`, XorgBig (KBRO, MUBR, MUBY, MUCU, RJOA, UGSB, ZMCK), BCSceneries Ligurian COAST D d/e/f, tsc777 EHEH, Skydom Red Sea (nur `_sp`), GlobalArt KBNA (die DSF setzt die Wald-Ordner `fal/spr/sum/win` alle gleichzeitig; die verschachtelte `library.txt` mit `EXPORT_SEASON` ist inaktiv).
- **Datumsregionen** (`sim/time/local_date_days`): XCodr KMMH, KTEX (nur Skifahrer/Skilichter), Ibertech EKVG 1 bis 3.
- **Nur Doku-Aussage:** Papickx EBCI.

AeroX EDDG (Doku: Schnee/Regen auf dem Boden) und VerticalSim KMSY (Regionen nass/feucht über `rain_percent`) sind Wetter, nicht Jahreszeit, und zählen als E.

Partielle `SEASONAL`-Packs (nur `_sp`): was X-Plane mit fehlenden `_fa`/`_wi` macht, ist nicht geprüft.

## 8. Bereits geändert

XCodr AEP: `/mnt/xplane_data/Scenery/XCodr/AEP Package/AEP/Library.txt`, Zeile 1330:

```
EXPORT_SEASON fal AEP/PrivateAssets/Falling_Leaves.obj	Effects/Blank.obj
```

Das fallende Laub im Herbst ist ausgeschaltet. Die Sicherung `Library.txt.vor-laub-aus-2026-10-10` unterscheidet sich nur in dieser Zeile (Ziel dort `Effects/Falling_Leaves.obj`; `diff` am 2026-10-24 geprüft). `Falling_Leaves_Yellow.obj` (Zeile 1335) fällt im Herbst weiter.

## 9. Checkliste

**Erkennung, in dieser Reihenfolge:**

1. Pack-Wurzel-`library.txt` mit `/usr/bin/grep -E 'EXPORT\w*SEASON|REGION_DREF|IF_SEASON'`. Das Muster `EXPORT\w*SEASON` deckt `EXPORT_SEASON`, `EXPORT_EXCLUDE_SEASON`, `EXPORT_RATIO_SEASON` und `EXPORT_EXTEND_SEASON`. Stufe 1 kannte nur drei davon.
2. **CRLF:** `\r` vorher entfernen (`tr -d '\r'`), sonst scheitern Zeilenende-Anker und Pfadprüfungen. Mehrere Packs (AEP) haben CRLF.
3. **Nur die `library.txt` im Pack-Wurzelordner zählt.** Kopien in Unterordnern (z. B. `SAM_DeveloperPack/library.txt`, `Seasons/winter/library.txt`) sind inaktiv, solange sie nicht über die Wurzel kopiert werden.
4. `SEASONAL <tex>` in `.for` (auch `.pol`, `.obj`). Dazu prüfen, welche `_sp/_su/_fa/_wi`-Texturen existieren.
5. Zielpfade der `EXPORT*`-Zeilen auf Existenz prüfen. Deklariert, aber leer oder ohne Ziele = D.
6. Das DSF als Binärdatei auf die benutzten Pfade durchsuchen (`grep -a -o`); `.dsf.txt` kann veraltet sein. Fest verdrahtete `Season_Summer/…`-Pfade sind nicht umschaltbar.
7. Ordner- und Dateinamen mit `Seasons`, `summer|autumn|winter`, auch fremdsprachig (`invierno`, `otoño`, `verano`, `nieve`, `Verão/Verao`, `inverno`, `hiver`, `neige`, `Herbst`, `Schnee`, `zima`, `talvi`, `syksy`). Das Vendor-Verzeichnis (Eltern) mitansehen: dort liegen Geschwister-Packs und Archive (`*SeasonPack*.7z`).
8. Doku (README, PDF mit `pdftotext`) nach `season|winter|snow|autumn`.

**Falsche Treffer (nicht zählen):** Schneepflug-/Räum-Objekte (`SnowPlow`, `snow_removal/*.agp`), `snowbird.obj`, `Rain_Var/Snow_*.pol` und `Wet/Dry`-Regionen sowie Doku-Aussagen zu Wettereffekten (Wetter, nicht Jahreszeit), `asfalto_nieve` (Wetter-Asphalt), `Fallback`/`Fallen`, `Spring.for` (Ortsname), Kleidungsvarianten von Personen-Objekten, `wet`-Wald-`.for` des Standardpakets, `aluminium`/`Iluminacao` (enthalten „lumi“), Optionsordner mit Statics, Mesh oder Gras (ULLI, KCLE, LOWW, KPHX). Ein `SAM_Seasons_SDK`-Ordner allein beweist nichts.

## 10. Zahlen

| Kategorie | Zeilen | davon neu im Lückenlauf | Packs |
|---|---|---|---|
| A | 8 | 0 | 7 |
| B | 62 | 9 | 58 |
| C | 23 | 0 | 11 |
| D | 15 | 0 | 15 |
| E (nicht in der TSV) | 391 | – | – |

Im Lückenlauf (535 verlinkte Packs) sind drei Stufe-1-Zeilen von E auf B geändert (tsc777 EHEH, XorgBig KBRO, Skydom Red Sea). Dazu kommen sechs neue B-Zeilen für Packs, die Stufe 1 gar nicht als Zeile hatte (BCSceneries Ligurian D d/e/f, Colombia `L_XPC_LuiMor_free`, Orbx `Global_Forests_v2`, `ChudobaDesign_Library`). Es gab keinen neuen Fund in A, C oder D. Das Muster `EXPORT_EXCLUDE_SEASON` kam in den verlinkten Packs nicht vor, die Namensprüfung auf fremdsprachige Jahreszeitwörter hatte keinen echten Treffer.

Review am 2026-10-24 (Codex, jede Aussage an den Dateien nachgeprüft): ZeroDollar zdp-library 1.2.0 von C auf D; CFXP CYLW neu als D (war E); GlobalArt KBNA neu als B (war E); XCodr `AEP1-4` neu als B (stand in keiner Liste); AeroX EDDG und VerticalSim KMSY von B auf E (nur Wetter), daher bleibt E bei 391. Dazu korrigiert: Rückweg bei Pearson CYYZ, Plugin-Zuordnung von `deepwinter`/`snowytrees` (nur SAM, das deaktiviert ist).

`verified = ja` haben 22 Zeilen: Ibertech LOWG, FlyTampa EKCH, Axonos KJAC, Kumiankka Oulu, GlobalArt Pearson, FlyAgi EDDK, aus dem Review CFXP CYLW, GlobalArt KBNA, XCodr `AEP1-4`, ZeroDollar zdp-library 1.2.0. Der Rest ist `nein`.

## 11. Offene Punkte

- Nichts im Sim geprüft: ob das openSAM-Menü die Regionen wirklich umschaltet, ob SAM nach Umbenennen von `SAM.xpl.xorg` wieder lädt (Betreiber-Entscheidung, nicht angefasst), was X-Plane mit fehlenden Exportzielen und fehlenden `SEASONAL`-Varianten macht.
- Nicht gelesen: `.docx`, `.doc`, Bild-PDFs (TaiModels OOMS, YBCS, EGCC, Newport News, ENGM), PDF-Handbücher über 40 MB.
- DSF nur als Strings durchsucht, nicht dekodiert; 7z-komprimierte DSF nicht geöffnet.
- Archive nur gelistet (`7z l`), nie entpackt (auch nicht `FlyTampa_EKCH_XP_SeasonPack.7z`, außer den zwei `library.txt` im Scratch).
- Exportziele nur relativ zum Pack geprüft, nicht über Packs hinweg.
- Fremdsprachige Doku-Aussagen sind nur über Dateinamen gesucht, nicht im Text.
