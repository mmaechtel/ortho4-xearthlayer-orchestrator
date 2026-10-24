# Bestandsaufnahme: wer liefert welches Mesh (Stand 2026-10-24)

> **Vorläufig. Detailprüfungen stehen noch aus.** Die Zahlen hat ein Subagent aus den DSF-Kopfdaten (`sim/overlay`, `sim/creation_agent`) und den `.ter` gelesen. Selbst nachgeprüft sind bisher nur EDLP und EDVK, außerdem ELLX und Korsika, die schon als vendor tile laufen. Bevor eine Zeile umgesetzt wird, wird sie einzeln geprüft (siehe „Offene Prüfungen“).

Gescannt wurden
- `scenery_packs.ini` mit 827 Einträgen,
- `~/.local/share/xearthlayer/patches/` und `patches.disabled/`,
- `ops/patches/` und die Spec `ops/packages/oxo_apt.toml`,
- Patch-Dateien aus Add-ons (`*.patch.osm`, `*.muxp`) unter Custom Scenery und `/mnt/xplane_data/Scenery`.

**Reihenfolge:** `zzXEL_ortho` steht in `scenery_packs.ini` auf Position 825 von 827. Jedes aktive Paket mit Basis-Mesh schlägt deshalb XEL und `A00_OXO` auf seiner Kachel. Innerhalb von XEL schlägt ein aktiver XEL-Patch jedes Paket, und `A00_OXO` schlägt die übrigen XEL-Pakete.

## 1. Eigene Kacheln (`A00_OXO`, 52 Kacheln, davon 5 vendor)

Auf den meisten gewinnt unsere Kachel, etwa bei EDDF, EDDM, LSZH, LFPG, LEBL, ENGM, ESSA, BIRK und LPPT. Diese hier sind verdeckt oder blockiert:

| Kachel | ICAO | Verdeckt durch | Status |
|---|---|---|---|
| `+51+008` | EDLP | Aerosoft EDLP 1-Airport: Laminar-Mesh, mit Maps2XPlane bearbeitet, aktiv, vor XEL | verdeckt, selbst geprüft |
| `+51+009` | EDVK | Aerosoft EDVK 1-Airport: wie EDLP | verdeckt, selbst geprüft |
| `+35+010` | DTMB | `FSDG-Monastir-Terrain`: Landklassen-Mesh, aktiv, vor XEL. Das Paket enthält `DTMB.patch.osm`, md5-gleich mit unserem | verdeckt, ungeprüft |
| `+51+000` | London | Orbx TE GB South: aktiv, zusätzlich als aktiver XEL-Patch | r2 wartet, wird nach dem Bau verdeckt sein |
| `+53-003` | EGCC | Orbx TE GB Central | wie London |
| `+32-017` | LPMA | `zOrthographic_+32-017` ist deaktiviert | ok |

## 2. Fremde Ortho-Kacheln für den vendor-Weg (Texturnamen passen auf XELs Muster)

| Kachel | Was | Provider | Bemerkung |
|---|---|---|---|
| `+52+004` | EHAM FlyTampa Amsterdam (`MUX`) | BI17/BI18 | Kandidat |
| `+59+030` | ULLI DigitalDesign (`MUXP`) | BI17/BI18, Arc19 | Kandidat |
| `+60+024`, `+60+025`, `+61+025` | Helsinki Metropolitan VFR 2025 | FIN17 | eigene Luftbilder; als vendor tile gingen sie verloren, deshalb Patch lassen |
| 43 Kacheln `ALPS_*` | OrthoStudio Alpen | BI16 (teils 17/18) | in `patches.disabled`, Mesh-Qualität ungeprüft (`creation_agent` osxp) |

Rest der Welt: 28 Kacheln (USA, Japan, Nepal, Philippinen, Ozeanien), Liste beim Subagenten.

## 3. Ortho, das XEL nicht streamen kann (bleibt so)

- **Orbx TrueEarth:** GB South mit 25 Kacheln, GB Central mit 12, GB North mit 35, die Balearen mit 7. Dazu Kanaren und USA mit zusammen 159.
- **Sonstige:** LICD Lampedusa `+35+012`.
- Unsere Kacheln dort gingen nur, wenn das ganze Orbx-Paket deaktiviert wird.

## 4. Patch vorhanden, aber noch keine eigene Kachel

- **`ops/patches` in Europa:** nichts offen.
- **LEMD Madrid** `+40-004`: Aerosoft liefert `Patches/+40-010/+40-004/LEMD.patch.osm` mit. Er ist neu und noch nicht in `ops/patches`.
- **BIRK:** Der Patch bei XorgBig unterscheidet sich (andere md5) von unserem, ein Vergleich steht aus.
- **Rest der Welt:** 71 Patch-Kacheln in `ops/patches` ohne Gruppe. KDEN und KABQ haben abweichende Add-on-Patches.
- **Nur MUXP:** GEML Melilla (Aerosoft), dazu Amsterdam und ULLI (die haben fertige Kacheln, siehe 2). Außerhalb Europas KSFO, UELL, EBCI-Papickx und Grenada.

## 5. Nur Mesh (keine Ortho-Texturen, kein Patch zum Bauen)

Alle sind aktiv und verdecken XEL auf der ganzen Kachel:

| Kachel | Was | Paket |
|---|---|---|
| `+51+008`, `+51+009` | EDLP, EDVK | Aerosoft Airport (Mesh steckt im Flughafen-Paket) |
| `+40-004` | LEMD Madrid | Aerosoft 2-Mesh (Patch siehe 4) |
| `+39+004` | LEMH Menorca | Aerosoft 02-Mesh (Maps2XPlane) |
| `+35-003` | GEML Melilla | Aerosoft 2-Mesh (nur MUXP) |
| `+35+010` | DTMB Monastir | FSDG-Monastir-Terrain |
| `+35+025` | LGIR Heraklion | Iberdesign |
| `+53+027`, `+53+028` | UMMS Minsk | Iberdesign |
| `+37+023`, `+37+024`, `+38+023`, `+38+024` | Athen | FlyTampa Athens 3 Mesh |
| `+55+012` | EKCH Kopenhagen | FlyTampa Copenhagen 3Mesh (Mischfall, ungeprüft) |
| `+61-007`, `+61-008`, `+62-007`, `+62-008` | Färöer | Faroes4XPlane |

Rest der Welt: Svalbard (77 Kacheln), Seychellen, Gesellschaftsinseln, St. Helena, St. Barth, CYUL, CYVR, CYLW, CYGK, KBNA, Las Vegas, NWWW, SBBR und SBCF.

Was hier möglich ist: das Mesh behalten oder das Paket deaktivieren bzw. unter `zzXEL_ortho` schieben. Dann gibt es XEL-Ortho, aber der Flughafen liegt auf samsoirs Mesh.

## Offene Prüfungen

- [ ] Je Zeile vor der Umsetzung: DSF-Kopf, `.ter`-Verweise und Reihenfolge in `scenery_packs.ini` einzeln nachsehen.
- [ ] EDLP und EDVK: Lässt sich der Flughafen ohne die Aerosoft-DSF betreiben (`apt.dat`, Objekte)? Wie hängen `Earth nav data.orig` bei EDVK und die DSF-Textfassung bei EDLP damit zusammen?
- [ ] DTMB: Steht hinter `FSDG-Monastir-Terrain` nur Mesh, oder braucht der Flughafen es?
- [ ] EKCH: Ortho oder Landklassen?
- [ ] OrthoStudio-Alpen: Mesh-Qualität im Vergleich zu `A00_OXO`.
- [ ] Helsinki FIN17: Bestätigen, dass XEL nur vom eingestellten Provider streamt (laut Log Apple Maps).
- [ ] BIRK, KDEN, KABQ: Unsere Patches mit denen der Add-ons vergleichen.
- [ ] Bei großen Overlay-Paketen hat der Scan nur 3 DSF je Paket als Stichprobe geprüft. READMEs, die einen Patch nur erwähnen, sind nicht durchsucht.
