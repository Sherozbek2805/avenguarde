# cube/phase4: the calibration

What the engine reads, and what is kept only as a record.

## Read by the engine

| file | what |
|---|---|
| `minmax_scale_summary.json`, `minmax_moon.npy` (and three larger `minmax_*.npy` files rebuilt by `build/phase4b_minmax_scale.py`) | each variable on the one shared min-max scale |
| `phase4c_summary.json`, `whiten_<set>.npy`, `center_<set>.npy` | group-wise whitening and the typical distance `d_bar` of the three full variable sets |
| `ranking_sets.json` and the `whiten_` / `center_` files of the sets named in it | the same for the sets that leave out what Earth cannot reach |
| `ref_pixels.npy`, `complete_mask.npy` | Earth's reference population: the cells of ice-free land, and which of them carry every variable |

## Kept as a record: results of the method before 11 November 2026

These files come from the first pass of 9 November, when the method ranked each world separately and used a threshold on the score. They are superseded (VARIABLES.md B33 to B38) and the engine does not read them.

| file | what it was |
|---|---|
| `phase4a_summary.json` | the per-world percentile transform |
| `phase4d_targets.json` | the Artemis targets under the first variable set |
| `phase5_null.json` | the first chance test, with a score threshold |
| `dimension_check.json`, `tpi7_dimension_check.json`, `target_spread_b36.json`, `minmax_description_b38.json`, `mars_thermal_1d_validation.json`, `svf_seam_*.json` | measurements and checks behind single decisions, cited in VARIABLES.md. Not superseded; not read by the engine |

Current results are in `runs/`.
