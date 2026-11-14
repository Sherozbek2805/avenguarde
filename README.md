# Terrestrial Analog Finder

NASA Space Apps Challenge 2026. Where on Earth is most like a place on the Moon or Mars?

Give the tool a region on the Moon or Mars. It scores every piece of Earth's ice-free land against it, ranks the result, tests the best match against chance, and says where the match holds, where it breaks, and what no place on Earth can offer.

**State on 14 November 2026:** the data cube, the calibration, the output contract and the specifications were finished before the hackathon. The engine (score, chance test, sites, description) was written on the first hackathon day and is in `engine/`.

## Run the engine

```bash
python build/phase4b_minmax_scale.py          # once: rebuilds three calibration files (30 s)
python engine/tests.py                        # the specification's tests
python engine/run.py moon Haworth             # one target, both ranking systems, maps and JSON
python engine/run_all.py moon                 # all nine Artemis regions
```

From Python:

```python
import sys; sys.path.insert(0, "engine")
from analog_engine import Pairing

P = Pairing("moon")                                               # load once, about 1 s
doc, detail, state = P.run_preset("Haworth", system="all_variables", out_dir="runs/haworth")
doc, detail, state = P.run_custom("circle", dict(lat=-43.3, lon=-11.4, radius_km=43),
                                  system="earth_reachable_only", name="Tycho", out_dir="runs/tycho")
click = P.point(state, lat=-24.05, lon=-69.92)                    # any Earth cell against that target
```

## The web API

For the website and the backend. It only calls the engine above.

```bash
pip install fastapi uvicorn
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

A search takes about 40 seconds for a 15-cell region and several minutes for a few hundred cells, so `/search` does not wait. Poll `/jobs/{job_id}` every few seconds, then fetch `/runs/{run_id}`. One search runs at a time; a shape of more than 1,500 cells is refused. `python engine/test_api.py` exercises all of it against a running server.

`doc` is the output of `contract/output_schema.json`; `click` is `contract/point_schema.json`. `system` is `all_variables` or `earth_reachable_only`: both are always run, and the team names one the main result. Results go to `runs/` (not in this repository: each run holds about 250 MB of full-resolution maps).

## Start here

| if you are | read |
|---|---|
| anyone | the animated explainer: `docs/Analog_Finder_Explained.html` (open in a browser) |
| writing the engine | `docs/TEST_SPEC_2026-11-10.md`, top to bottom. Then `docs/NULL_TABLE_DESIGN_2026-11-10.md` |
| building the website | `contract/README.md`, then the three `contract/example_*.json` files |
| checking a decision | `VARIABLES.md`, the decision log. Sections B33 to B38 hold the method as it stands |
| looking for a source | `SOURCES.md` |

The full method is `docs/analog_finder_method_spec_rev10.docx`.

## The method in ten lines

1. **Grid.** Earth, the Moon and Mars on equal-area cells (HEALPix), about 6 to 7 km across on all three.
2. **Variables.** Terrain (slope, roughness at four scales, landform position, open sky), temperature (level, day–night swing, seasonal swing on Mars), rock (silica, iron oxide). 12 for Earth–Moon, 13 for Earth–Mars.
3. **One scale.** Each variable is put on one min-max scale shared by Earth and the target world.
4. **Whitening.** Double counting is removed inside each group of variables, using Earth's own pattern.
5. **Target.** Nine Artemis III regions and six NASA Exploration Zones on Mars are built in; a user can draw their own.
6. **Score.** An Earth cell's score is its mean distance to every cell of the target. Cells are then ranked: the best 1%, the best 5%.
7. **Chance test.** 1,000 random patches of the same size and latitude; one control (a patch of the Atacama).
8. **Sites.** Cells of the best 1% that touch each other are one place.
9. **Describe.** Every variable, its gap in real units, and three lists per site: succeeds, fails, beyond Earth.
10. **Output.** One JSON file and a few maps per run (`contract/`).

## What is in this repository

| path | what |
|---|---|
| `build/` | the scripts that built the cube and the calibration. One script per step; run them one at a time |
| `cube/healpix/` | the cube: 131 layers, one `.npy` file each (12 × Nside² values; Nside 1024 Earth, 256 Moon, 512 Mars) |
| `cube/cube_manifest.json` | every layer: units, source, gates, provenance |
| `cube/phase4/` | the calibration: reference population, whitening matrices, typical distances |
| `contract/` | the output contract (version 2.4), examples, preset targets, the use table |
| `docs/` | specifications, the method spec, figures, the explainer |
| `export/site_assets/` | map tiles of the layers and the catalogues, for the website |
| `sources/` | only the small tables this project wrote (targets, lookups, the analog-site catalogue) |

## What is NOT here, and how to get it

- **Three calibration files over GitHub's 100 MB limit.** Rebuild them in about 30 seconds:

  ```bash
  python build/phase4b_minmax_scale.py
  ```

  It writes `cube/phase4/minmax_earth_moon.npy`, `minmax_earth_mars.npy` and `minmax_mars.npy` from the layers in `cube/healpix/`.
- **The raw downloads** (about 30 GB) and the full-resolution elevation grids (30 GB). `SOURCES.md` lists where each came from. They are needed only to rebuild a layer, not to run the engine.
- `cube/phase4/percentiles.npy`, a diagnostic the engine must not read.

## Check your copy

```bash
python build/cube_validate.py
```

It must print `PASS`. Python 3.11 or later with `numpy`, `scipy`, `astropy`, `astropy-healpix`, `jsonschema`.

The scripts find the project folder from their own location. To point them elsewhere, set `ANALOG_ROOT`.

## Honest limits

- No place on Earth copies lunar or martian gravity, air pressure, radiation or day length. Every site is a partial analog.
- Mars temperatures are modelled, not measured. Earth's rock chemistry is a lookup by rock class.
- One cell is 6 to 7 km across. Nothing here describes boulders or soil.
- The examples in `contract/` carry real cube values and PLACEHOLDER scores and p-values. Results exist only after the engine has run.

## Data sources

All input data is public. Each derived layer names its source in `cube/cube_manifest.json` and `SOURCES.md`: LOLA and MOLA elevation, ETOPO 2022, MODIS land-surface temperature, LRO Diviner, Lunar Prospector, TES, GLiM (Hartmann & Moosdorf 2012), SCAR GeoMAP (Cox et al. 2023), Gard et al. 2019, the Artemis III candidate regions (NASA, 28 October 2024) and NASA's 2015 Exploration Zone workshop.

## AI use

Built with Claude (Anthropic) under the team's direction; every method decision was made by the team and is recorded in `VARIABLES.md`.
