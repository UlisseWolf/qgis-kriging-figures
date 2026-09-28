# QGIS Kriging Figures

[![QGIS](https://img.shields.io/badge/QGIS-3.x-589632?logo=qgis&logoColor=white)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A collection of **QGIS Processing scripts** that automatically generate publication-ready multi-panel figures (theses, papers, technical reports) from geostatistical interpolation rasters (kriging).

Each script produces both a **composite figure** (side-by-side panels with a shared legend) and a **standalone version of every panel**, complete with title, north arrow, scale bar and legend, ready to be placed on its own in a document.

> **Note:** the scripts' user interface, log messages and in-code comments are in Italian. This README documents parameters using their Italian labels as they appear in QGIS, with an English description.

---

## Table of Contents

- [Key Features](#key-features)
- [Included Scripts](#included-scripts)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [1. Kriging grid (range × model)](#1-kriging-grid-range--model)
  - [2. KED vs UNMIG comparison](#2-ked-vs-unmig-comparison)
  - [3. P10 / P50 / P90 percentiles](#3-p10--p50--p90-percentiles)
- [Common Parameters](#common-parameters)
- [Outputs](#outputs)
- [Technical Notes](#technical-notes)
- [Troubleshooting](#troubleshooting)
- [Repository Structure](#repository-structure)
- [License](#license)

---

## Key Features

- **Consistent color scale** across all comparable panels: min/max computed automatically over the whole raster group (or set manually).
- **Zero-centered diverging scale** for difference panels (±max|Δ|), so positive and negative deviations are immediately readable.
- **Same extent, scale and symbology** on every panel.
- **Optional vector overlays**: measurement points (wells) and the outline of a reference water body (lake), with uniform styling.
- **Automatic cartographic elements**: north arrow, alternating double-graduated scale bar with "nice" rounded values (1‑2‑5‑10…), panel labels `a)`, `b)`, `c)`…
- **Adaptive layout**: labels and legends are sized by measuring the actual rendered text, so nothing gets clipped regardless of system fonts.
- **Accurate legends**: legend colors are sampled from the exact ramp applied to the rasters, not an approximation.
- **Any color ramp** available in the QGIS Style Manager (Spectral, RdYlBu, Viridis, RdBu…), with optional inversion.

## Included Scripts

| Script | Name in the Processing Toolbox | Output figure |
|---|---|---|
| [`export_griglia_kriging.py`](scripts/export_griglia_kriging.py) | *Esporta griglia kriging (range x modello)* | Panel matrix: rows = variogram range, columns = model (spherical, exponential, gaussian…) |
| [`export_ked_unmig_diff.py`](scripts/export_ked_unmig_diff.py) | *Esporta confronto KED-UNMIG* | 3 panels: `KED` \| `UNMIG` \| `KED − UNMIG` |
| [`export_p10_p50_p90.py`](scripts/export_p10_p50_p90.py) | *Esporta P10-P50-P90 + differenza* | 4 panels: `P10` \| `P50` \| `P90` \| `P90 − P10` |

All scripts appear under the **Tesi - Kriging** group in the Processing Toolbox.

## Requirements

- **QGIS 3.x** (Python and GDAL are included in the standard installation)
- **Pillow** in the QGIS Python environment, required to compose the final figures

If Pillow is not available, the scripts still export the raw PNG panels and log a warning that the final composition was skipped. To install it:

```bash
# Windows – from the OSGeo4W Shell
pip install pillow

# Linux / macOS – using the Python interpreter bundled with QGIS
python3 -m pip install pillow
```

## Installation

1. Download or clone the repository:
   ```bash
   git clone https://github.com/UlisseWolf/qgis-kriging-figures.git
   ```
2. Copy the files in `scripts/` to the Processing scripts folder of your QGIS profile:

   | Operating system | Path |
   |---|---|
   | Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\processing\scripts` |
   | Linux | `~/.local/share/QGIS/QGIS3/profiles/default/processing/scripts` |
   | macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/processing/scripts` |

   Alternatively, from QGIS: *Processing Toolbox → Scripts icon → Open Scripts Folder*.
3. Restart QGIS, or right-click **Scripts** in the Processing Toolbox and reload scripts from the folder.

## Usage

### 1. Kriging grid (range × model)

Visually compares how different variogram models and range values affect the interpolated surface.

**Main input**: a semicolon-separated CSV file mapping each raster to its position in the grid. The order in which rows and columns first appear in the CSV defines their order in the figure. Column headers must be kept exactly as shown.

```csv
riga;colonna;percorso_raster
10 m;Sferico;C:/data/sph_10.tif
10 m;Esponenziale;C:/data/exp_10.tif
10 m;Gaussiano;C:/data/gau_10.tif
500 m;Sferico;C:/data/sph_500.tif
500 m;Esponenziale;C:/data/exp_500.tif
500 m;Gaussiano;C:/data/gau_500.tif
```

`riga` = row label, `colonna` = column label, `percorso_raster` = raster path. The labels are free text and are printed as-is in the figure, so they can be in any language. A sample file is available at [`examples/config_griglia.csv`](examples/config_griglia.csv).

**Specific parameters**

| Parameter (QGIS label) | Description | Default |
|---|---|---|
| CSV di configurazione | `riga;colonna;percorso_raster` file | — |
| Usa min/max manuali | Use the manual values below instead of computing them | `False` |
| Min / Max manuale | Color scale bounds | — |
| Larghezza / Altezza singolo pannello | Size of each panel in pixels | `900 × 700` |

The common extent is the union of all raster extents (plus the lake extent, if provided).

### 2. KED vs UNMIG comparison

Compares a surface obtained with Kriging with External Drift (KED) against a reference raster (e.g. the Italian national UNMIG dataset) and shows their difference.

Since the reference raster may cover a much larger area (e.g. an entire country), the script **automatically clips and realigns** it to the KED raster grid using `gdal.Warp` (same extent, resolution, row/column count and CRS, bilinear resampling). As a result:

- the shared min/max is computed over the study area only;
- the difference can be computed cell by cell.

**Input modes**

| UNMIG raster | Difference raster | Behavior |
|:---:|:---:|---|
| ✅ | — | UNMIG is clipped; `KED − UNMIG` is computed |
| ✅ | ✅ | UNMIG is clipped; the supplied difference is used |
| — | ✅ | UNMIG is reconstructed as `KED − difference` |
| — | — | Error: at least one of the two is required |

The KED raster is always required and defines the study area.

### 3. P10 / P50 / P90 percentiles

Displays the percentiles of a probabilistic estimate or simulation, together with the width of the uncertainty interval `P90 − P10`.

- P10, P50 and P90 share the same linear scale (min/max computed jointly over the three rasters).
- The `P90 − P10` difference is computed with the QGIS Raster Calculator, or can be supplied precomputed through the dedicated optional parameter.

## Common Parameters

| Parameter (QGIS label) | Description | Default |
|---|---|---|
| Shapefile pozzi | Optional point layer (wells), drawn as black circles with a white outline | — |
| Shapefile lago | Optional polygon or line layer (lake), drawn as a blue outline | — |
| Cartella di output | Destination folder for all generated files | — |
| Rampa colore | Name of a ramp from the QGIS Style Manager | `Spectral` |
| Inverti rampa | Invert the main ramp | `False` |
| Rampa divergente | Ramp for difference panels *(KED‑UNMIG and P10‑P90 only)* | `RdBu` |
| Inverti rampa differenza | Invert the diverging ramp *(KED‑UNMIG and P10‑P90 only)* | `False` |
| Includi la lettera identificativa | Also print `a)`, `b)`… on the standalone panels | `True` |

Ramp names are case-sensitive. If a ramp cannot be found, the script falls back to a default ramp and reports it in the log.

## Outputs

| Script | Composite figure | Raw panels | Standalone panels | Intermediate rasters |
|---|---|---|---|---|
| Kriging grid | `griglia_finale.png` | `pannello_<row>_<column>.png` | `pannello_<row>_<column>_singolo.png` | — |
| KED‑UNMIG | `ked_unmig_differenza.png` | `pannello_KED.png`, `pannello_UNMIG.png`, `pannello_KED_-_UNMIG.png` | `pannello_<name>_singolo.png` | `unmig_ritagliato.tif` or `unmig_ricostruito.tif`, `differenza_ked_unmig.tif` |
| P10‑P50‑P90 | `p10_p50_p90_differenza.png` | `pannello_P10.png` … `pannello_P90_-_P10.png` | `pannello_<name>_singolo.png` | `differenza_p90_p10.tif` |

Spaces in file names are replaced with `_`.

## Technical Notes

- **Coordinate reference system**: the scale bar assumes a projected CRS in meters (e.g. UTM). If the rasters' CRS is not metric, the script logs a warning since the scale bar may be inaccurate.
- **Main-thread execution**: all algorithms set `FlagNoThreading`, because rendering with `QPainter`/`QImage` on a background thread can crash QGIS.
- **Synchronous rendering**: maps are rendered with `QgsMapRendererCustomPainterJob`, which is more stable inside Processing than parallel jobs.
- **Layer order**: wells on top, lake below the wells, raster in the background.
- **Fonts**: the scripts try Arial, Calibri and DejaVu Sans in order; if none is found, they fall back to Pillow's default font while still honoring the requested size (Pillow ≥ 9.2).
- **Vector layer labels**: the legend labels the overlays as "Pozzi" (wells) and "Lago di Bracciano" (Lake Bracciano, the original study area). To adapt the scripts to a different study area, just edit these strings in the code.

## Troubleshooting

| Problem | Solution |
|---|---|
| The script does not appear in the Toolbox | Check the scripts folder of the active profile, then reload scripts or restart QGIS |
| "Pillow non installato" warning | Install Pillow in the QGIS Python environment (see [Requirements](#requirements)) |
| Error computing the difference | Rasters must share the same extent, resolution and row/column count; alternatively, supply a precomputed difference raster |
| Clipping UNMIG does not produce a valid raster | Make sure KED and UNMIG have compatible CRSs |
| The color ramp is not applied | Check the exact name (case-sensitive) under *Settings → Style Manager* |
| Scale bar missing or wrong | Use rasters in a projected CRS with meter units |

## Repository Structure

```
qgis-kriging-figures/
├── scripts/
│   ├── export_griglia_kriging.py
│   ├── export_ked_unmig_diff.py
│   └── export_p10_p50_p90.py
├── examples/
│   └── config_griglia.csv
├── .gitignore
├── LICENSE
└── README.md
```

## License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 [UlisseWolf](https://github.com/UlisseWolf)
