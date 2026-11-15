# Output contract 2.4 — for the website developer

Frozen 10 November 2026. Changed four times on 11 November as the method was decided; **2.4 is the version to build against.** This page describes 2.4 only. The history is in `../VARIABLES.md` (B33 to B39).

| file | what it is |
|---|---|
| `output_schema.json` | JSON Schema (draft 2020-12) for one engine run. Authoritative. |
| `point_schema.json` | JSON Schema for the click payload: any Earth cell against the current target. |
| `example_output.json` | A run whose chance test is at the floor ("p < 0.001"). Target: Haworth, Moon. |
| `example_output_null.json` | The same run with a non-significant result (p = 0.418). **Build against both.** |
| `example_point.json` | A click on the McMurdo Dry Valleys. |
| `make_examples.py` | Regenerates the three examples from the real cube and validates them. |
| `use_table.json` | The fixed table that turns verdicts into "succeeds / fails / beyond Earth" lines. For the engine; the website only shows the result. |
| `targets_moon.json`, `targets_mars.json` | The preset targets: nine Artemis III regions and six NASA Exploration Zones on Mars. Pixel lists, cell counts, sources. |
| `targets_ranking.json` | Per preset target: which variables Earth can match and which it cannot, with the gap in physical units. |
| `control_fixtures.json` | The pixels of the Atacama control. For the engine. The file also holds the fixtures of two controls that were dropped on 11 November (a negative control and an Apollo control); the engine does not use them. |
| `../export/site_assets/` | Static map tiles of the cube layers and the catalogues as GeoJSON. |

**The three `example_*.json` files show the SHAPE of the output. They are not results.** They were written before the engine existed. Every physical value, position, Köppen class, rock class, coordinate and catalogue distance in them is read from the cube. Every `di_*`, `p`, rank, patch size and control is a placeholder. `code_version` is `"EXAMPLE-NOT-A-RESULT"`. Never quote a distance from an example file.

**Real results are in `../runs/`** (since 14 November 2026): one `output.json` per target and ranking system, in exactly this format, for example `../runs/moon_haworth__all_variables/output.json`. Build the website against those. Keep `example_output.json` only to test the "significant" case, which no real target reaches.

## What changed in 2.4 — read this if you built against 2.3

- **Three fields are renamed.** `earth_percentile` → `earth_position`, `target_percentile` → `target_position`, `percentile_gap` → `position_gap`. The scale is now min-max: a position is (value − lowest) / (highest − lowest), where lowest and highest are taken over Earth and the target world together. A position of 0.3 means "30% of the way from the smallest value to the largest".
- **`run.scale` is `"minmax"`.**
- **One control.** `null_test.negative_control` and `null_test.second_positive_control` are gone. `positive_control` (the Atacama patch) stays.
- **Sites are patches.** `run.site_rule` is always `"patches_of_top_share"`. `exclusion_km` and `exclusion_source` are gone. Every site has `patch_cells` and `patch_area_km2`.
- **`use_case` (one sentence) is replaced by `use` (three lists).** See "The use block" below. The click payload has it too.

## The things that will bite you

1. **There are two ranking systems, and `run.ranking.system` says which one made the file.** `all_variables`: everything ranks. `earth_reachable_only`: variables Earth cannot reach are shown and left out of the ranking. **The main result is `all_variables`** (decided 14 November 2026): show it first. `earth_reachable_only` is the second view, behind a switch. For a preset target you get a file from each.
2. **DI values are large, and that is not a bug.** The score is a cell's mean distance to every cell of the target, and the targets are varied inside. For an Artemis region even the best Earth cell will score well above 1. **Lead with ranks and bands, not with DI.** Show `d_bar_target` (the target's own spread) beside any DI you print.
3. **`dims_used` differs between runs and DI is not comparable across it.** Ranks are: "best 1%" means best 1% in every run.
4. **Temperature is beyond Earth for every preset target.** Under `earth_reachable_only` those rows carry `ranked: false`, and a Moon run has no thermal score: `di_group.thermal` is `null` and there is no `di_thermal` map. Show `physical_gap` with its unit: "103 K colder than Earth's coldest ground".
5. **A populated `sites[]` is not a result.** Lead with the chance-test line: `p`, `di_observed` against `null_median`. Print "not significant" as plainly as "significant". No adjectives.
6. **Any per-group field can be `null`.** Render "no data", not zero.
7. **`sites[]` can be empty and has at most 20 entries.** `run.patches_total` can be larger; say "20 of 57 places".
8. **`lithology.source` is `GLiM` or `GeoMAP`, and `l1_code` means different things in each.** Always show `description`, never the bare code.
9. **Every Mars preset has four files:** with and without composition, under each ranking system. Show "without composition" first and label the other "with composition, N of M cells".

## The top-X% slider

`rank_combined` gives every scored Earth cell its place in the order: 0 is the best cell on Earth for this target, 1 the worst.

- The PNG is data, not a picture. Each pixel is one grey value v (0–255). **rank = (v / 255)².** Transparent means "not in the ranking population" (ice, water, missing data).
- **To show the best X%:** keep the pixels with `v <= 255 * sqrt(X)`. Best 1% is `v <= 25`; best 5% is `v <= 57`; best 10% is `v <= 80`. Do it in the browser (a canvas or a shader). No call to the backend, so the slider is instant.
- **Default view:** the two bands in `run.rank_bands`, best 1% in the strong colour and best 5% in a lighter one. Let the slider run from 0.1% to 20%.
- **Readout beside the slider:** "best X% of Earth's ice-free land = N cells ≈ A km²". One cell is 40.5 km²; the ranking population is about 3.2 million cells, so 1% is about 32,000 cells, 1.3 million km².
- **Wording.** A best 1% exists for every target, even a hopeless one. Say "the best 1% of Earth for this target", never "99% similar". There is no "percent alike" number in the output; do not invent one.

## The use block

Every site, and every click, carries `use`:

- `succeeds`: what the site can be used for, because those variables agree.
- `fails`: what it must not be used for, because those variables differ. **Always show it next to `succeeds`.**
- `beyond_earth`: what no place on Earth can offer for this target.
- `general`: one sentence, present only when `succeeds` is empty.

Each line has a `group` (terrain, thermal, composition), a `label`, the `variables` behind it and a ready `text`. Show the text as written. Three columns or three coloured lists both work.

Under them, show the fixed `earths_limits` block (gravity, air, radiation, day length, weathering) on every result page.

## Pages

1. **Landing.** Two tiles: analogs for a Moon base, analogs for a Mars site.
2. **Target.** The body in three views (global plate carrée, north polar, south polar stereographic). A list of preset targets from `export/site_assets/catalogue/targets_moon_artemis3.geojson` and `targets_mars.geojson`: each is a point with its shape in the properties. Draw the shape. Custom shapes (circle, rectangle) call the backend.
3. **Result.** In this order:
   - the chance-test line, stated plainly;
   - the percentile map (`rank_combined`: best 1% and 5%, with the slider), site markers, and the known-analog catalogue as a second layer;
   - the switch between the two ranking systems;
   - the distance map (`di_combined`) and one group map per group that has a ranked variable, as toggles;
   - click any cell for the point panel;
   - the site list as cards: rank, patch area, group bars, the variable rows, `use`, Köppen class, rock class, known or new;
   - the `earths_limits` block.

The demo path uses precomputed JSON and PNG only. Only a custom target calls the backend.

## Number formatting — correctness rules, not style

| field | rule |
|---|---|
| `lat`, `lon` | fixed 2 decimals (`-77.52`, `161.85`) |
| `di_*`, `d_bar_*`, `spread` | 3 significant figures |
| `position_gap` | signed, 2 decimals (`+0.12`, `−0.31`) |
| `earth`, `target_median`, `physical_gap` | 3 significant figures with the unit; temperatures in K |
| `p` | if `p_at_floor`: "p < 0.001"; else 2 significant figures |
| counts, ranks | integers |

## Static layers

`export/site_assets/layers.json` lists, per body, the display layers with file names, units, colour range and colormap. Six per body where they exist: roughness 21 km, landform position 21 km, sky view, temperature level, day–night range, SiO₂. They do not depend on the target and can be shown before any search.

## Colour and state

Absent or masked pixels are transparent in every PNG; draw them as neutral grey, never as a low value. Mark modelled layers (the Mars temperatures) with a visible tag. Mark weak variables (composition) with a visible tag.
