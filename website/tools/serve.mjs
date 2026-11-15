// A tiny static server for local use: node tools/serve.mjs [port]  →  http://127.0.0.1:8080  (answers this computer only)
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
// Inside the repository the site sits in website/ and the engine's files are one level up (runs, contract, export, docs).
// A request for data/runs/... that is not found in website/data is then read from there, so nothing is copied.
const REPO = resolve(ROOT, '..'), SHARED = ['runs', 'contract', 'export', 'docs'];
const PORT = Number(process.argv[2]) || 8080;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json', '.geojson': 'application/json', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.txt': 'text/plain; charset=utf-8' };

createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  let file = normalize(join(ROOT, p));
  const m = /^\/data\/([a-z]+)\//.exec(p);
  if (m && SHARED.includes(m[1]) && !existsSync(file)) {
    const up = normalize(join(REPO, p.slice('/data/'.length)));
    if (up.startsWith(join(REPO, m[1]))) file = up;
  }
  const inside = file.startsWith(ROOT) || SHARED.some((d) => file.startsWith(join(REPO, d)));
  if (!inside || !existsSync(file) || !statSync(file).isFile()) { res.writeHead(404); res.end('Not found'); return; }
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
  createReadStream(file).pipe(res);
}).listen(PORT, '127.0.0.1', () => console.log(`Terrestrial Analog Finder: http://127.0.0.1:${PORT}  (this computer only; close this window to stop)`));
