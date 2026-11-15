# Terrestrial Analog Finder

NASA Space Apps Challenge 2026. Where on Earth is most like a place on the Moon or Mars?

Give the tool a region on the Moon or Mars. It scores every piece of Earth's ice-free land against it, ranks the result, checks the best match against chance, and says where the match holds, where it breaks, and what no place on Earth can offer.

**State on 15 November 2026:** the data cube, the calibration and the specifications were prepared before the hackathon weekend. The engine (score, check against chance, sites, description), the web API and all results were made on 14 November and are in `engine/` and `runs/`.

## The result in short

- **15 NASA targets, 42 result sets.** Nine Artemis III candidate regions at the lunar south pole and six Mars Exploration Zones, each under two ranking systems. The Mars zones are also run with and without rock composition.
- **Where Earth comes closest:** the Altiplano and Atacama, the Tibetan Plateau and the summit of Mauna Loa. High, cold, dry, bare ground.
- **Closest is not close.** No target passes the check against chance. The main reason is temperature: the Artemis regions are about 50 to 105 K colder than the coldest ice-free ground on Earth.
- **A plausibility check.** The engine is never given a list of analog sites. This is how much of five well-known analog regions falls inside Earth's best 1% (by chance: 1%):

| region | Moon, 9 targets | Mars, 6 targets |
|---|---|---|
| Atacama and Altiplano | 64% | 52% |
| Qaidam basin | 69% | 15% |
| Hawaii, Big Island (Mauna Loa) | 25% | 0% |
| Antarctic Dry Valleys | 2% | 14% |
| Iceland | 0% | 0% |

  Medians over the main-system runs; the regions are rough boxes (`build/known_regions.py`, `runs/known_regions.json`). It is a check, not a validation: temperature carries much of the score.

Every result file is in `runs/`. The full method and the result tables are in `docs/analog_finder_method_spec_rev11.docx`.

## Start here

| if you are | read |
|---|---|
| anyone | the animated explainer: `docs/Analog_Finder_Explained.html` (open in a browser) |
| a judge | `docs/analog_finder_method_spec_rev11.docx` (10 pages), then `runs/README.md` |
| building the website | `contract/README.md`, then a real result such as `runs/moon_haworth__all_variables/output.json` |
| checking a decision | `VARIABLES.md`, the decision log. Sections B33 to B39 hold the method as it stands |
| looking for a source | `SOURCES.md` |
| asking how AI was used | `AI_USE.md` |

## The method in ten lines

1. **Grid.** Earth, the Moon and Mars on equal-area cells (HEALPix), about 6 to 7 km across on all three.
2. **Variables.** Terrain (slope, roughness at four scales, landform position at two scales, open sky), temperature (level, day–night swing, seasonal swing on Mars), rock (silica, iron oxide). 12 for Earth–Moon, 13 for Earth–Mars.
3. **One scale.** Each variable is put on one min-max scale shared by Earth and the target world.
4. **Whitening.** Double counting is removed inside each group of variables, using Earth's own pattern.
5. **Target.** Nine Artemis III regions and six NASA Exploration Zones on Mars are built in; a user can draw their own.
6. **Score.** An Earth cell's score is its mean distance to every cell of the target. Cells are then ranked: the best 1%, the best 5%.
7. **Check against chance.** 1,000 random patches of the same size and latitude (a Monte Carlo test); one control (a patch of the Atacama).
8. **Sites.** Cells of the best 1% that touch each other are one place.
9. **Describe.** Every variable, its gap in real units, and three lists per site: succeeds, fails, beyond Earth.
10. **Output.** One JSON file and a few maps per run (`contract/`).

Two ranking systems are always run. **The main result is `all_variables`** (the team's decision, 14 November 2026, after both had been run on all fifteen targets). `earth_reachable_only` leaves out the variables Earth cannot reach and is the second view.

## Data

All input data is public. Each derived layer names its source in `cube/cube_manifest.json` and `SOURCES.md`.

| world | dataset | used for |
|---|---|---|
| Moon | LRO LOLA global elevation model, `LOLA_Global_LDEM_118m_Mar2014` (118 m) | terrain |
| Moon | LRO Diviner global cumulative products, `LRO-L-DLRE-5-GCP-V1.0` | temperature |
| Moon | Lunar Prospector GRS element abundances, 2° (Prettyman et al. 2006) | silica, iron oxide |
| Mars | MOLA – HRSC blended elevation model, 200 m (MGS MOLA with ESA Mars Express HRSC; USGS Astrogeology) | terrain |
| Mars | MGS TES thermal inertia (Putzig & Mellon 2007) and albedo; dust climatology (Montabone et al. 2015); KRC model (Kieffer 2013) | temperature, **modelled** |
| Mars | MGS TES mineral maps (Bandfield 2002) | silica, iron oxide |
| Earth | ETOPO 2022, 15 arc-second (NOAA NCEI) | terrain |
| Earth | MODIS land surface temperature, MOD11C3 and MYD11C3 (Terra, Aqua) | temperature |
| Earth | GLiM rock map (Hartmann & Moosdorf 2012), SCAR GeoMAP (Cox et al. 2023), checked against Gard et al. 2019 | silica, iron oxide |
| Earth | Köppen–Geiger climate classes (Beck et al. 2023); USGS terrestrial analog sites catalogue (doi:10.5066/P9J72921) | describing sites; never ranked |
| Earth | WorldClim 2.1 (land mask); MODIS MCD43A3 albedo (a stored layer that does not rank) | supporting layers |
| targets | NASA Artemis III candidate regions (28 October 2024), polygons as published by LROC QuickMap; NASA Exploration Zone workshop, 2015 | the fifteen targets |

`SOURCES.md` ends with the same list with product names and references.

## Run the engine

Python 3.11 or later.

```bash
pip install -r requirements.txt
python build/phase4b_minmax_scale.py          # once: rebuilds three calibration files (30 s)
python engine/tests.py                        # the specification's tests
python engine/run.py moon Haworth             # one target, both ranking systems, maps and JSON
python engine/run_all.py moon                 # all nine Artemis regions
```

From Python:

```python
import sys; sys.path.insert(0, "engine")
from analog_engine import Pairing

P = Pairing("moon")                                               # load once
doc, detail, state = P.run_preset("Haworth", system="all_variables", out_dir="runs/haworth")
doc, detail, state = P.run_custom("circle", dict(lat=-43.3, lon=-11.4, radius_km=43),
                                  system="earth_reachable_only", name="Tycho", out_dir="runs/tycho")
click = P.point(state, lat=-24.05, lon=-69.92)                    # any Earth cell against that target
```

`doc` follows `contract/output_schema.json`; `click` follows `contract/point_schema.json`.

`python engine/tests.py` reports 46 of 47 checks passed. The one that does not, test [17], is known: one group distance is estimated on two different random subsamples and differs by 0.9% (`VARIABLES.md` B39a). `engine/tests_custom.py` passes 14 of 14 and `engine/tests_mars_custom.py` 5 of 5.

A drawn area on the Moon takes about 40 seconds at 25 km radius, 2 minutes at 50 km and 10 minutes at 100 km. On Mars a zone of 680 cells takes about 10 minutes.

## The web API

For the website and the backend. It only calls the engine above.

```bash
python -m uvicorn api:app --app-dir engine --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/docs`: every endpoint is listed there with a "Try it out" button.

| call | what it does |
|---|---|
| `GET /presets?body=moon` | the preset targets: name, centre, shape, number of cells |
| `GET /runs` | finished runs on disk, newest first |
| `GET /runs/{run_id}` | one run: the contract's output JSON |
| `GET /runs/{run_id}/files/{name}` | a map of that run, for example `rank_combined_global.png` |
| `POST /search` | start a search; answers at once with a `job_id` |
| `GET /jobs/{job_id}` | `queued`, `running`, `done` (with `run_id`) or `failed` (with the reason) |
| `GET /point?run_id=..&lat=..&lon=..` | any Earth cell against that run's target (the click payload) |

A search body is one of:

```json
{"body": "moon", "system": "all_variables", "preset": {"name": "Haworth"}}
{"body": "moon", "system": "earth_reachable_only", "name": "my crater",
 "selection": {"method": "circle", "params": {"lat": 9.6, "lon": -20.1, "radius_km": 14}}}
```

`/search` does not wait. Poll `/jobs/{job_id}` every few seconds, then fetch `/runs/{run_id}`. One search runs at a time; a shape of more than 1,500 cells is refused. `python engine/test_api.py` exercises all of it against a running server.

## What is in this repository

| path | what |
|---|---|
| `engine/` | the search engine, the web API and their tests |
| `runs/` | the results: one folder per target and ranking system, with `output.json` and the maps |
| `build/` | the scripts that built the cube and the calibration. One script per step; run them one at a time |
| `cube/healpix/` | the cube: 131 layers, one `.npy` file each (12 × Nside² values; Nside 1024 Earth, 256 Moon, 512 Mars) |
| `cube/cube_manifest.json` | every layer: units, source, gates, provenance |
| `cube/phase4/` | the calibration: reference population, whitening matrices, typical distances |
| `contract/` | the output contract (version 2.4), shape examples, preset targets, the use table |
| `docs/` | the method specification, the test specification, figures, the explainer, the pitch |
| `export/site_assets/` | map tiles of the layers and the catalogues, for the website |
| `sources/` | only the small tables this project wrote (targets, lookups, the analog-site catalogue) |

## What is NOT here, and how to get it

- **Three calibration files over GitHub's 100 MB limit.** Rebuild them in about 30 seconds:

  ```bash
  python build/phase4b_minmax_scale.py
  ```

  It writes `cube/phase4/minmax_earth_moon.npy`, `minmax_earth_mars.npy` and `minmax_mars.npy` from the layers in `cube/healpix/`.
- **The full-resolution result maps** (`*_nside1024.npy`, 48 MB each) that `output.json` names under `rasters[].file`. The PNG maps of every run are here. Recreate the rest with `python engine/run_all.py moon` or `mars`.
- **The raw downloads** (about 30 GB) and the full-resolution elevation grids (30 GB). `SOURCES.md` lists where each came from. They are needed only to rebuild a layer, not to run the engine.
- `cube/phase4/percentiles.npy`, a diagnostic the engine must not read.

## Check your copy

```bash
python build/cube_validate.py
```

It must print `PASS`. On a clone it also lists five warnings, "not in this copy", for the working-resolution elevation grids under `cube/dem/`: they are not in the repository and the engine does not need them.

The scripts find the project folder from their own location. To point them elsewhere, set `ANALOG_ROOT`. A clone is about 1.5 GB, most of it the cube. `cube/cube_manifest.json` keeps each layer's original local path (`source_absolute`) as a record; it is not used.

## Honest limits

- No place on Earth copies lunar or martian gravity, air pressure, radiation or day length. Every site is a partial analog.
- No target passes the check against chance. The closest ground on Earth is still far from the lunar pole and from Mars, mainly in temperature.
- Mars temperatures are modelled, not measured. Earth's rock chemistry is a lookup by rock class.
- One cell is 6 to 7 km across. Nothing here describes boulders or soil.
- The three `contract/example_*.json` files show the SHAPE of the output and carry placeholder scores. Real results are the `output.json` files in `runs/`.
- A few steps of the animated explainer use invented numbers to show an idea. Each says so on screen.

## Use of AI

An AI assistant, Claude (Anthropic), was used for the code, the documents and the slides, under the team's direction. Every method decision was made by the team and is dated in `VARIABLES.md`. No image, map, audio or video is AI-generated, and no data is: every number comes from the public datasets through this code. The full statement is `AI_USE.md`.

## Licence

MIT (see `LICENSE`). The source datasets keep their own licences; see `SOURCES.md`.
