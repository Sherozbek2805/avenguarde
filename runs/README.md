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

- `moon_summary.json`: one line per run, both systems side by side.
- `moon_system_comparison.json`: the three questions of `docs/TEST_SPEC_2026-11-10.md` section 7, answered for both systems.
- `_controls/`: the Atacama control, once per variable set.

**Not in the repository:** the full-resolution maps (`*_nside1024.npy`, 48 MB each) that `output.json` names under `rasters[].file`. Recreate a run with `python engine/run.py moon Haworth`, or all of them with `python engine/run_all.py moon`.

**Read the results with these in mind** (they are also written in every `output.json` under `limits`):

- No Artemis region is significant under either ranking system.
- The Atacama control FAILED under `earth_reachable_only` (p = 0.11) and passed under `all_variables`.
- The score is a cell's mean distance to every cell of the target, so a target that is varied inside scores worse whatever Earth looks like. Read ranks, not score values.
