# Null-table design — for the engine, hackathon day

For Shokhrukh. First written 10 November 2026; **rewritten clean on the night of 11 November** after the final decisions (VARIABLES.md B36 to B38). No table is computed before the day; this is the design only.

## Why a table at all

One chance test is 1,000 searches. That is fine for the preset targets, which run once and are cached. It is slow for a user who draws a shape on the website and waits.

So: compute the null distributions in advance, on a grid of **latitude band × patch size**, and look the answer up.

**The table is optional.** A custom target of 100 cells or fewer runs a live null in under a minute. Build the table only if time is left after the contract tests pass.

**Two paths, one statistic.**

| target | null | `null_source` in the output |
|---|---|---|
| preset (9 Artemis regions, 6 Mars zones, the Atacama control) | live: exact cell count, band = centre |latitude| ± 2° (written per target in `contract/targets_*.json`) | `live` |
| custom (drawn by the user) | looked up in the table, or live if no table fits | `precomputed_table` or `live` |

The statistic is the same in both: **the minimum `di_combined` over the fixed 100,000-cell Earth sample**, where `di_combined` is the mean distance to all of the patch's cells, on the variables the real target ranks on.

## What one table entry is

For one variable set, one band, one patch size:

1. Draw a random centre in the band. Uniform in area: draw sin(latitude) uniformly between the band edges, a random sign for the hemisphere, a uniform longitude.
2. The patch is the centre's N nearest **complete** cells (great-circle distance). If the centre has no complete cell within twice the nominal patch radius, discard and redraw. Count the discards.
3. Run the ordinary distance code on that patch. Record the minimum `di_combined` over the Earth sample, and the patch's own spread (mean distance between its cells / d_bar; test spec 25).
4. Repeat until B = 1,000 minima are stored.

Store the 1,000 minima **sorted**, as float32.

## The grid

**Build the table for ONE ranking system: the one the team names the main result on the day.** Do not build it before that choice.

| axis | values | count |
|---|---|---|
| variable set, if the main system is `all_variables` | the three parent sets: Earth–Moon (12), Earth–Mars (13), Earth–Mars without composition (11) | 3 |
| variable set, if the main system is `earth_reachable_only` | Moon without both temperatures (10); Mars without composition, without level and day–night swing (9) | 2 |
| |latitude| band edges, degrees | 0, 15, 30, 45, 60, 75, 85, 90 | 7 bands |
| patch size N, cells | 10, 30, 100, 300 | 4 |

That is 84 or 56 distributions of 1,000 numbers each, under 0.5 MB.

Under `earth_reachable_only` a custom target can rank on a list that is not in the table (a lunar equatorial target keeps its temperature level, for example). **Then it uses the live null.** The engine compares the target's ranked-variable list and d_bar with the table's and refuses a table that does not match.

Why these bands: 15° steps follow the thermal gradient well enough, and the last 15° is split at 85° because the Artemis targets sit there.

Why these sizes: one cell is about 7 km across on both bodies. 10 cells is a crater about 25 km wide; 300 cells is a region about 135 km wide.

**A target larger than 300 cells** gets no table p-value. The Mars preset zones are about 680 cells: live null only.

## Lookup rule — always the conservative neighbour

A custom target has N cells and a centre |latitude|.

- **Band:** the band that contains the centre. If the target crosses a band edge, use both bands and report the **larger** p.
- **Size:** N usually falls between two tabulated sizes. Compute p against both and report the **larger** p. Record the size that gave it in `patch_cells`.

The larger p is the safe direction. A table may make a result look less significant than a live null would. It must never make it look more.

## p from a table

Same formula as live: `p = (1 + count of table minima ≤ di_observed) / (1 + 1000)`.

`di_observed` must be computed on **the same 100,000-cell Earth sample** the table was built with. Save the sample's index array once (`null_tables/earth_sample.npy`) and load it everywhere.

## File layout

```
cube/null_tables/
  earth_sample.npy                  # 100,000 cell indices, int64, fixed
  null_moon.npz                     # minima[set, band, size, 1000]  float32, sorted on the last axis
  null_mars.npz
  null_tables.json                  # everything needed to check them, below
```

`null_tables.json` records: code version, date, seed, B, the ranking system, the band edges, the sizes, the variable list and d_bar of each set, the number of discarded draws per entry, the null median and the median patch spread per entry, and the SHA-256 of `earth_sample.npy`.

**The tables die with the cube.** If any ranking layer is rebuilt, or a variable is added or dropped, delete the tables and recompute.

## Cost — timing only

Measured on 11 November on the 16-core laptop with 3,245,417 Earth cells, 10 whitened variables and random stand-in rows. Every distance was thrown away. These are times, not results.

| target or patch size | one full DI map | one null draw (100,000 cells) | 1,000 null draws |
|---|---|---|---|
| 15 cells | 0.4 s | 12 ms | 0.2 min |
| 90 cells | 1.8 s | 56 ms | 0.9 min |
| 300 cells | 5.6 s | 170 ms | 2.8 min |
| 680 cells | 13.5 s | 414 ms | 6.9 min |

Ranking 3.2 million scores for the percentile bands: 0.4 s.

One (set, band) row of the table, sizes 10 + 30 + 100 + 300, is about 4.5 minutes. 21 rows (three sets) are about 1.6 hours; 14 rows (two sets) about 1 hour.

**The preset targets, all of them, under both ranking systems:** nine Artemis regions twice (seconds each), six Mars zones four times each (about 7 minutes each): about 3 hours of null runs if done one after another. Start them as soon as the Atacama control has passed, Moon first.

What the benchmark did NOT time: drawing a compact patch for each null draw and looking up its positions. Time 20 real draws before starting a long run. On a small cloud server with 2 cores, expect five to eight times slower.

## Tests for the table

1. **Table against live.** For three preset targets, compute p both ways. The table p must be ≥ the live p minus 0.05.
2. Every stored distribution has exactly 1,000 finite values, sorted.
3. Rebuilding one entry with the same seed gives identical numbers.
4. Print the table of null medians once and look at it: it should change smoothly along both axes. A jump is a bug in the band sampling.
5. The polar band (85–90°) patches are compact blobs, not rings.
6. A table built for one variable set is refused for a target with another.

## What goes in the output

For a table lookup the output carries `null_source: "precomputed_table"`, the band actually used in `band_abs_lat`, the size actually used in `patch_cells`, B = 1000, and the table's seed. The result page shows `di_observed` next to `null_median`, as for a live null.

**Wording (Sherozbek, 11 November).** The chance test is shown as it comes out. "Not significant, p = 0.42" is printed as plainly as "significant". No adjectives, no hiding.
