// Copies the backend files the site reads from the repository into data/, keeping the same relative paths.
// Usage: ANALOG_REPO=/path/to/avenguarde node tools/sync-data.mjs
// Without ANALOG_REPO it makes a shallow sparse clone of the public repository (used on Render).
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import { tmpdir } from 'node:os';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(SITE, 'data');
const REPO_URL = 'https://github.com/Sherozbek2805/avenguarde';

let repo = process.env.ANALOG_REPO;
if (!repo) {
  repo = join(tmpdir(), 'avenguarde-sync');
  if (!existsSync(join(repo, '.git'))) {
    execSync(`git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} "${repo}"`, { stdio: 'inherit' });
    execSync('git sparse-checkout set contract runs export docs', { cwd: repo, stdio: 'inherit' });
  }
}
if (!existsSync(join(repo, 'contract', 'README.md'))) {
  console.error(`No repository at ${repo}. Set ANALOG_REPO to a clone of ${REPO_URL}.`);
  process.exit(1);
}

let files = 0, bytes = 0;
function copy(rel) {
  const src = join(repo, rel);
  if (!existsSync(src)) { console.error(`MISSING in the repository: ${rel}`); process.exitCode = 1; return; }
  const dst = join(OUT, rel);
  mkdirSync(dirname(dst), { recursive: true });
  cpSync(src, dst);
  files += 1; bytes += statSync(src).size;
}

// fixed files
['contract/targets_moon.json', 'contract/targets_mars.json',
 'runs/moon_summary.json', 'runs/mars_summary.json',
 'export/site_assets/layers.json',
 'export/site_assets/catalogue/targets_moon_artemis3.geojson',
 'export/site_assets/catalogue/targets_mars.geojson',
 'docs/explainer/scenes.js', 'docs/explainer/data.js'].forEach(copy);

// the global basemap of each body, as named by layers.json (the site does not use the polar pictures)
const layers = JSON.parse(readFileSync(join(repo, 'export/site_assets/layers.json'), 'utf8'));
for (const body of Object.values(layers.bodies)) copy('export/site_assets/' + body.basemap.global);

// every run named by the two summary files: its output and its rank picture (global view)
for (const s of ['runs/moon_summary.json', 'runs/mars_summary.json']) {
  for (const run of JSON.parse(readFileSync(join(repo, s), 'utf8'))) {
    const out = JSON.parse(readFileSync(join(repo, run.out_dir, 'output.json'), 'utf8'));
    if (out.contract_version !== '2.4') { console.error(`${run.out_dir}: contract_version is ${out.contract_version}, expected 2.4`); process.exitCode = 1; }
    copy(run.out_dir + '/output.json');
    const rank = out.rasters.find((r) => r.name === 'rank_combined');
    copy(rank.views.global);
  }
}
console.log(`data/: ${files} files, ${(bytes / 1048576).toFixed(1)} MB, from ${repo}`);
