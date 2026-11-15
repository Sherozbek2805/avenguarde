// The flat map of Earth for the results page: relief in grey, the rank picture coloured over it, the best places as outlines.
// rank_combined is data (contract 2.4): grey value v, rank = (v / 255)^2, transparent = no rank. Best X% = v <= 255 * sqrt(X).
const css = () => getComputedStyle(document.documentElement);
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
// A picture that does not arrive in two minutes is reported, so a page never waits without end on a broken connection.
const loadImage = (src, ms = 120000) => new Promise((ok, no) => {
  const i = new Image(); i.crossOrigin = 'anonymous';
  const t = setTimeout(() => { i.onload = i.onerror = null; i.src = ''; no(new Error('the map did not arrive in two minutes; the connection is too slow or was cut. Reload the page to try again')); }, ms);
  i.onload = () => { clearTimeout(t); ok(i); }; i.onerror = () => { clearTimeout(t); no(new Error('cannot load ' + src)); }; i.src = src;
});

export class EarthMap {
  // host: a positioned element the map fills. inset: { left, right, top, bottom } in CSS px kept clear for panels.
  constructor(host, inset) {
    this.host = host; this.inset = inset; this.W = 2880; this.H = 1440;
    this.cv = Object.assign(document.createElement('canvas'), { className: 'map__canvas', tabIndex: 0 });
    this.cv.setAttribute('aria-label', 'Map of Earth. Drag to move, scroll to zoom.');
    host.append(this.cv);
    this.off = document.createElement('canvas'); this.off.width = this.W; this.off.height = this.H;
    this.sites = []; this.share = 0.01; this.chosen = -1; this.hover = -1; this.k = 0;
    this.reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    new ResizeObserver(() => this.resize()).observe(host);
    this.bind();
  }

  async load(reliefUrl, rankUrl) {
    const [relief, rank] = await Promise.all([loadImage(reliefUrl), loadImage(rankUrl)]);
    const read = (img, filter) => { const c = document.createElement('canvas'); c.width = this.W; c.height = this.H; const g = c.getContext('2d', { willReadFrequently: true }); if (filter) g.filter = filter; g.drawImage(img, 0, 0, this.W, this.H); return g.getImageData(0, 0, this.W, this.H).data; };
    const a = read(relief, 'grayscale(1)'), b = read(rank), n = this.W * this.H;
    this.L = new Uint8Array(n); this.v = new Uint8Array(n); this.has = new Uint8Array(n);
    for (let i = 0; i < n; i++) { this.L[i] = a[i * 4]; this.v[i] = b[i * 4]; this.has[i] = b[i * 4 + 3] > 127 ? 1 : 0; }
    this.img = this.off.getContext('2d').createImageData(this.W, this.H); this.out = new Uint32Array(this.img.data.buffer);
    this.compose(); this.fit(); this.draw();
  }

  // colour the rank picture for the chosen share
  compose() {
    const c = css(), [pr, pg, pb] = rgb(c.getPropertyValue('--primary').trim()), [ar, ag, ab] = rgb(c.getPropertyValue('--answer').trim()), [nr, ng, nb] = rgb(c.getPropertyValue('--no-rank').trim());
    const thr = 255 * Math.sqrt(this.share), { L, v, has, out } = this, none = 0xff000000 | (nb << 16) | (ng << 8) | nr;
    const tint = new Float32Array(256); for (let i = 0; i < 256; i++) tint[i] = 0.8 * Math.pow(1 - i / 255, 1.7);   // stronger where the land is more like the target
    for (let i = 0; i < out.length; i++) {
      if (!has[i]) { out[i] = none; continue; }
      const g = 24 + L[i] * 0.34;
      if (v[i] <= thr) out[i] = 0xff000000 | ((ab * 0.9 + g * 0.1) << 16) | ((ag * 0.9 + g * 0.1) << 8) | (ar * 0.9 + g * 0.1);
      else { const t = tint[v[i]]; out[i] = 0xff000000 | ((g + (pb - g) * t) << 16) | ((g + (pg - g) * t) << 8) | (g + (pr - g) * t); }
    }
    this.off.getContext('2d').putImageData(this.img, 0, 0);
  }
  setShare(x) { this.share = x; if (this.L) { this.compose(); this.draw(); } }

  // sites: [{ lat, lon, label }]. Each gets the outline of the connected best-share area that holds its best cell.
  setSites(sites, topShare) {
    const { W, H, v, has } = this, thr = 255 * Math.sqrt(topShare), lab = this.lab = new Int8Array(W * H), inBand = (i) => has[i] && v[i] <= thr;
    this.sites = sites.map((s, n) => {
      const px = Math.min(W - 1, Math.floor((s.lon + 180) / 360 * W)), py = Math.min(H - 1, Math.floor((90 - s.lat) / 180 * H));
      const site = { ...s, x: px + 0.5, y: py + 0.5, edges: null, box: [px, py, px + 1, py + 1] };
      let seed = -1;   // the best cell can fall between pixels: look up to 3 pixels around it
      for (let r = 0; r <= 3 && seed < 0; r++) for (let dy = -r; dy <= r && seed < 0; dy++) for (let dx = -r; dx <= r; dx++) {
        const x = px + dx, y = py + dy; if (x < 0 || y < 0 || x >= W || y >= H) continue;
        const i = y * W + x; if (inBand(i) && !lab[i]) { seed = i; break; }
      }
      if (seed < 0) return site;
      const stack = [seed], cells = []; lab[seed] = n + 1;
      while (stack.length && cells.length < 400000) {
        const i = stack.pop(); cells.push(i); const x = i % W, y = (i - x) / W;
        for (const j of [x > 0 ? i - 1 : -1, x < W - 1 ? i + 1 : -1, y > 0 ? i - W : -1, y < H - 1 ? i + W : -1]) if (j >= 0 && !lab[j] && inBand(j)) { lab[j] = n + 1; stack.push(j); }
      }
      const e = []; let x0 = W, y0 = H, x1 = 0, y1 = 0;
      for (const i of cells) {
        const x = i % W, y = (i - x) / W; x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + 1); y1 = Math.max(y1, y + 1);
        if (x === 0 || lab[i - 1] !== n + 1) e.push(x, y, x, y + 1);
        if (x === W - 1 || lab[i + 1] !== n + 1) e.push(x + 1, y, x + 1, y + 1);
        if (y === 0 || lab[i - W] !== n + 1) e.push(x, y, x + 1, y);
        if (y === H - 1 || lab[i + W] !== n + 1) e.push(x, y + 1, x + 1, y + 1);
      }
      site.edges = Float32Array.from(e); site.box = [x0, y0, x1, y1];
      return site;
    });
    this.draw();
  }

  area() { const b = this.host.getBoundingClientRect(), i = this.inset; return { x: i.left, y: i.top, w: b.width - i.left - i.right, h: b.height - i.top - i.bottom, W: b.width, H: b.height }; }
  // The whole map, centred in the clear area. With no room yet (a hidden or tiny window) nothing is drawn until there is.
  fit() { const a = this.area(); if (a.w < 40 || a.h < 40) { this.k = 0; this.fitted = true; return; } this.k0 = Math.min(a.w / this.W, a.h / this.H); this.k = this.k0; this.ox = a.x + (a.w - this.W * this.k) / 2; this.oy = a.y + (a.h - this.H * this.k) / 2; this.fitted = true; }
  // The window or a panel changed size: fit again, unless the user has moved or zoomed the map.
  resize() { if (!this.L) return; if (this.fitted || !(this.k > 0)) this.fit(); else { const a = this.area(); if (a.w >= 40 && a.h >= 40) this.k0 = Math.min(a.w / this.W, a.h / this.H); } this.draw(); }

  // The map never leaves its frame: when it is smaller than the clear area it stays centred; when it is larger, its edges
  // cannot be pulled inside the clear area. So there is no dark space to drift into.
  clamp() {
    const a = this.area(), w = this.W * this.k, h = this.H * this.k;
    this.ox = w <= a.w ? a.x + (a.w - w) / 2 : Math.min(a.x, Math.max(a.x + a.w - w, this.ox));
    this.oy = h <= a.h ? a.y + (a.h - h) / 2 : Math.min(a.y, Math.max(a.y + a.h - h, this.oy));
  }

  draw() {
    if (!this.L || !(this.k > 0)) return;
    this.clamp();
    const a = this.area(), d = Math.min(2, window.devicePixelRatio || 1), cv = this.cv;
    if (cv.width !== Math.round(a.W * d) || cv.height !== Math.round(a.H * d)) { cv.width = Math.round(a.W * d); cv.height = Math.round(a.H * d); }
    const g = cv.getContext('2d'), c = css(), tok = (n) => c.getPropertyValue(n).trim(), { k, ox, oy } = this;
    g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, a.W, a.H);
    // the map and the outlines are drawn inside one fixed frame (the clear area); nothing shows under the header or the panel
    const frame = () => { g.save(); g.beginPath(); g.rect(a.x, a.y, a.w, a.h); g.clip(); };
    frame(); g.imageSmoothingEnabled = k < 1.5; g.drawImage(this.off, ox, oy, this.W * k, this.H * k); g.restore();
    g.font = `500 15px ${tok('--f-mono')}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round';
    // where each number would go, and which ones are shown: a number is left out when it would cover a better-ranked one
    // (zoom in to see them all); the place under the pointer always shows its number
    const tags = this.sites.map((s) => {
      const bw = (s.box[2] - s.box[0]) * k, bh = (s.box[3] - s.box[1]) * k, cx = ox + s.x * k, cy = oy + s.y * k, big = s.edges && Math.max(bw, bh) >= 12;
      return { big, cx, cy, x: (big ? ox + s.box[2] * k : cx + 9) + 15, y: (big ? oy + s.box[1] * k : cy - 9) - 6, w: g.measureText(s.label).width + 16,
        inside: cx >= a.x - 4 && cx <= a.x + a.w + 4 && cy >= a.y - 4 && cy <= a.y + a.h + 4 };
    });
    const shown = [], strongFirst = this.sites.map((s, i) => i).sort((p, q) => (q === this.hover || q === this.chosen) - (p === this.hover || p === this.chosen) || p - q);
    for (const i of strongFirst) { const t = tags[i]; t.show = t.inside && (i === this.hover || i === this.chosen || !shown.some((o) => Math.abs(o.x - t.x) < (o.w + t.w) / 2 + 2 && Math.abs(o.y - t.y) < 28)); if (t.show) shown.push(t); }
    const order = this.sites.map((s, i) => i).sort((p, q) => (p === this.chosen) - (q === this.chosen) || (p === this.hover) - (q === this.hover) || q - p);
    for (const i of order) {
      const s = this.sites[i], t = tags[i], strong = i === this.chosen || i === this.hover, w = i === this.chosen ? 2.5 : strong ? 2 : 1.5;
      frame(); g.beginPath();
      if (t.big) { const e = s.edges; for (let j = 0; j < e.length; j += 4) { g.moveTo(ox + e[j] * k, oy + e[j + 1] * k); g.lineTo(ox + e[j + 2] * k, oy + e[j + 3] * k); } }
      else g.arc(t.cx, t.cy, 9, 0, 7);   // too small to trace or to see: a ring at the best cell
      g.lineWidth = w + 2; g.strokeStyle = 'rgba(0,0,0,0.7)'; g.stroke(); g.lineWidth = w; g.strokeStyle = tok('--white'); g.stroke(); g.restore();
      if (!t.show) { s.tag = null; continue; }
      g.fillStyle = i === this.chosen ? tok('--primary') : tok('--surface-1'); g.beginPath(); g.roundRect(t.x - t.w / 2, t.y - 13, t.w, 26, 3); g.fill();
      if (i !== this.chosen) { g.lineWidth = 1; g.strokeStyle = strong ? tok('--white') : tok('--outline-2'); g.stroke(); }
      g.fillStyle = i === this.chosen ? tok('--on-primary') : tok('--on-surface'); g.fillText(s.label, t.x, t.y + 0.5);
      s.tag = { x: t.x, y: t.y, w: t.w };
    }
  }

  // what is under a CSS point: { site (index or -1), lat, lon, rank (0..1 or null) }
  at(px, py) {
    const x = (px - this.ox) / this.k, y = (py - this.oy) / this.k;
    let site = -1;
    this.sites.forEach((s, i) => { if (s.tag && Math.abs(px - s.tag.x) <= s.tag.w / 2 + 2 && Math.abs(py - s.tag.y) <= 15) site = i; else if (site < 0 && Math.hypot(px - (this.ox + s.x * this.k), py - (this.oy + s.y * this.k)) <= 11) site = i; });
    if (x < 0 || y < 0 || x >= this.W || y >= this.H) return { site, lat: null, lon: null, rank: null };
    const i = Math.floor(y) * this.W + Math.floor(x);
    if (site < 0 && this.lab && this.lab[i]) site = this.lab[i] - 1;
    return { site, lat: 90 - y / this.H * 180, lon: x / this.W * 360 - 180, rank: this.has[i] ? (this.v[i] / 255) ** 2 : null };
  }

  view(k, cxMap, cyMap, animate = true) {   // centre the map point (cxMap, cyMap) in the clear area at scale k
    if (!(this.k > 0)) return;
    const a = this.area(); k = Math.max(this.k0, Math.min(this.k0 * 16, k)); this.fitted = false;
    const to = { k, ox: a.x + a.w / 2 - cxMap * k, oy: a.y + a.h / 2 - cyMap * k }, from = { k: this.k, ox: this.ox, oy: this.oy };
    cancelAnimationFrame(this.fly);
    if (this.reduced || !animate) { Object.assign(this, to); this.draw(); return; }
    const t0 = performance.now(), ms = parseFloat(css().getPropertyValue('--t-move')) || 700;
    const step = (now) => { const t = Math.min(1, (now - t0) / ms), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.k = from.k + (to.k - from.k) * e; this.ox = from.ox + (to.ox - from.ox) * e; this.oy = from.oy + (to.oy - from.oy) * e; this.draw(); if (t < 1) this.fly = requestAnimationFrame(step); };
    this.fly = requestAnimationFrame(step);
  }
  centre() { const a = this.area(); return [(a.x + a.w / 2 - this.ox) / this.k, (a.y + a.h / 2 - this.oy) / this.k]; }
  zoomBy(f) { const [x, y] = this.centre(); this.view(this.k * f, x, y); }
  reset() { this.view(this.k0, this.W / 2, this.H / 2); this.fitted = true; }
  flyToSite(i) { const s = this.sites[i], a = this.area(), bw = Math.max(40, s.box[2] - s.box[0]), bh = Math.max(40, s.box[3] - s.box[1]);
    this.view(Math.min(this.k0 * 8, 0.45 * Math.min(a.w / bw, a.h / bh)), (s.box[0] + s.box[2]) / 2, (s.box[1] + s.box[3]) / 2); }

  bind() {
    const cv = this.cv; let down = null;
    const pos = (e) => { const b = cv.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
    cv.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, moved: 0 }; cv.setPointerCapture(e.pointerId); cancelAnimationFrame(this.fly); });
    cv.addEventListener('pointermove', (e) => {
      if (down) { const dx = e.clientX - down.x, dy = e.clientY - down.y; down.x = e.clientX; down.y = e.clientY; down.moved += Math.abs(dx) + Math.abs(dy); this.ox += dx; this.oy += dy; if (down.moved >= 5) this.fitted = false; this.draw(); }
      else if (this.L) this.onhover?.(this.at(...pos(e)));
    });
    cv.addEventListener('pointerup', (e) => { if (down && down.moved < 5 && this.L) this.onpick?.(this.at(...pos(e)).site); down = null; });
    cv.addEventListener('pointercancel', () => { down = null; });
    cv.addEventListener('pointerleave', () => this.onhover?.(null));
    cv.addEventListener('wheel', (e) => {
      e.preventDefault(); if (!this.L || !(this.k > 0)) return; cancelAnimationFrame(this.fly); this.fitted = false;
      const [px, py] = pos(e), k = Math.max(this.k0, Math.min(this.k0 * 16, this.k * Math.exp(-e.deltaY * 0.0015)));
      this.ox = px - (px - this.ox) * k / this.k; this.oy = py - (py - this.oy) * k / this.k; this.k = k; this.draw();
    }, { passive: false });
    cv.addEventListener('keydown', (e) => {
      const [x, y] = this.centre(), s = 80 / this.k, key = e.key;
      if (key === 'ArrowLeft') this.view(this.k, x - s, y); else if (key === 'ArrowRight') this.view(this.k, x + s, y);
      else if (key === 'ArrowUp') this.view(this.k, x, y - s); else if (key === 'ArrowDown') this.view(this.k, x, y + s);
      else if (key === '+' || key === '=') this.zoomBy(1.6); else if (key === '-') this.zoomBy(1 / 1.6); else return;
      e.preventDefault();
    });
  }
}
