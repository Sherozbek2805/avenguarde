# Website: Terrestrial Analog Finder

The team's website for the NASA Space Apps Challenge 2026. It shows the engine's results: the places on Earth
most like a region on the Moon or Mars.

Live: https://avenguarde.eengineer.net

## What is here

| Path | What it is |
|---|---|
| `index.html` | Home: the opening screen, the two worlds, "How the search works", Notes |
| `explore.html` | Choose a target on a globe (NASA's listed targets, or any place on the Moon) |
| `results.html` | The Earth map for one target: ranks, the chance test, the list of places |
| `place.html` | One place: its picture, the variables one by one, what it can be used for |
| `css/`, `js/` | Styles and scripts. Plain HTML, CSS and JavaScript with Canvas; no framework and no build step |
| `js/method/` | The scenes of "How the search works", a shorter set of `docs/explainer` |
| `fonts/`, `img/` | Fonts (with their licence), the pictures, the logo, light copies of the three base maps |
| `data/countries.json` | Country outlines for the Earth map (Natural Earth) |
| `tools/serve.mjs` | A small local web server |
| `server/engine-setup-v2.sh` | The script that set up the public server |

## Run it on your computer

You need Node.js.

```
node website/tools/serve.mjs
```

Then open http://127.0.0.1:8080. On Windows you can double-click `website/start-server.bat` instead.

The website reads the engine's files from this repository: `runs/`, `contract/` and `export/site_assets/`.
The local server finds them one folder up, so nothing has to be copied.

## Settings

All settings are in `js/config.js`.

| Setting | Meaning |
|---|---|
| `ENABLED_BODIES` | Which worlds are offered: `moon`, `mars`, or both |
| `DEFAULT_TARGET` | The target that is chosen when a page opens |
| `MAIN_SYSTEM` | The ranking system shown first (`all_variables`, the team's decision of 14 November 2026) |
| `API_BASE` | The address of the live engine. Empty text switches every live feature off; the stored results still work |
| `CUSTOM_BODIES` | Worlds where a visitor may pick any place on the globe. It needs the live engine |
| `CUSTOM_RADIUS_KM` | The smallest, largest and first radius of such a place |
| `PLACE_PICTURES` | Where the picture of a place comes from. For NASA sources only, set `['bluemarble']` |

## What the website reads

It follows contract 2.4. It reads `runs/moon_summary.json` and `runs/mars_summary.json`, then for each run its
`output.json` and `rank_combined_global.png`, the target lists in `contract/`, and the layers in
`export/site_assets/`. It does not read the example files in `contract/`.

## The live engine and the public server

The public site runs on one AWS Lightsail server (Ubuntu 24.04, Sydney). `server/engine-setup-v2.sh` is the
script that set it up at first boot. It clones this repository, starts the engine from `engine/api.py` unchanged,
and serves the website and the stored results.

Two things on that server are not in the engine:

- **A cache of the chance test's random draws.** The 1,000 draws depend only on the body, the variable set, the
  patch size, the latitude band and the fixed seed, so they are the same every time. The server keeps them on
  disk. A warm-up ran every main preset twice and compared p with the stored value: all 18 Moon runs and all
  24 Mars runs matched. The result file still says `null_source: "live"`.
- **An upload address for new versions of the website.** It needs a secret token. The token is not in this
  repository; in the script it is replaced by a placeholder.

Only one search runs at a time; a second one waits.

## Sources and licences

- **Pictures of places:** Sentinel-2 cloudless 2020 by EOX IT Services GmbH (contains modified Copernicus
  Sentinel data 2020), licence CC BY-NC-SA 4.0. If it does not answer, NASA GIBS Blue Marble is used.
- **Country outlines:** Natural Earth, public domain.
- **Fonts:** Google Sans Flex and Google Sans Code, SIL Open Font License (`fonts/OFL.txt`).
- **Base maps:** light copies of the engine's own `basemap_global.png` files.
- **Logo:** the team's own.

## Use of AI

- The website's code and text were written with Claude (Anthropic), under the team's direction.
- The opening picture (`img/hero.jpg`) and the two globe pictures (`img/globe-moon.png`, `img/globe-mars.png`)
  were made with Google Flow, an AI tool. They are decoration only; every map, number and result on the site
  comes from the engine's files.

## Known limits

- Tested in Chrome on a laptop. Firefox, Safari and phones were not tested on the public site.
- On a phone the methodology scenes are small.
- A new place on the Moon takes about 40 seconds to search, because its chance test is drawn fresh.
