# Results

One folder per run: `<body>_<target>__<ranking system>`. Every preset target is run under BOTH ranking systems, and both are kept. Nothing is left out because it is not significant.

| file | what |
|---|---|
| `output.json` | the run, in the contract format (`contract/output_schema.json`, version 2.4) |
| `rank_combined_global.png`, `_north.png`, `_south.png` | DATA for the top-X% slider: grey value v, rank = (v / 255)², transparent = no rank |
| `di_combined_*.png`, `di_terrain_*.png`, `di_thermal_*.png`, `di_composition_*.png` | pictures of the score and of each group's score (bright = alike) |
| `run_detail.json` | timings, the target's own spread against the random patches' spreads, the control's details |
| `null_draws.npz` | the 1,000 chance draws: each patch's best score, its own spread, its hemisphere |

Also here:

- `moon_summary.json`, `mars_summary.json`: one line per run, both systems side by side.
- `moon_system_comparison.json`, `mars_system_comparison.json`: the three questions of `docs/TEST_SPEC_2026-11-10.md` section 7, answered for both systems.
- `known_regions.json`: how much of five well-known analog regions falls inside Earth's best 1% and 5% (`build/known_regions.py`). A plausibility check, not a validation.
- `_controls/`: the Atacama control, once per variable set.
- `moon_haworth_summary.json`: the first single-target run of the engine, kept as it was written. `moon_summary.json` supersedes it.

Folder names: nine lunar targets (`moon_<target>__<system>`), six Mars targets without rock composition (`mars_<target>__<system>`) and with it (`mars_<target>_all_dimensions__<system>`). 42 result sets in all.

**The main result is `all_variables`** (the team's decision, 14 November 2026). The `earth_reachable_only` folder of the same target is the second view. Both are kept and both are shown.

**Not in the repository:** the full-resolution maps (`*_nside1024.npy`, 48 MB each) that `output.json` names under `rasters[].file`. Recreate a run with `python engine/run.py moon Haworth`, or all of them with `python engine/run_all.py moon`.

`run.code_version` in some files ends in `+engine-uncommitted`: those runs were made on 14 November before the engine was committed. The engine code is the one in `engine/`. No number was changed afterwards; one sentence of `limits` was updated in every file when the main ranking system was chosen (`VARIABLES.md` B39f).

**Read the results with these in mind** (they are also written in every `output.json` under `limits`):

- No target, on the Moon or on Mars, is significant under either ranking system.
- The Atacama control FAILED under `earth_reachable_only` (Moon p = 0.11; Mars p = 0.51 and 0.71) and passed under `all_variables` (p = 0.001). Under `all_variables` it passes partly because random patches of the Moon or Mars lie far from Earth in temperature.
- The score is a cell's mean distance to every cell of the target, so a target that is varied inside scores worse whatever Earth looks like. Read ranks, not score values.
