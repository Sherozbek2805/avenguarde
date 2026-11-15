// A globe on 2D canvases (no WebGL): relief pictures wrapped on a sphere, orthographic view.
// Drag turns it, the wheel zooms it, shapes given in longitude and latitude are drawn on top.
const RAD = Math.PI / 180, DEG = 180 / Math.PI;

export class GlobeView {
  // host: a positioned element the globe fills. opts: lat, lon, zoom, minZoom, maxZoom, offsetX (CSS px the centre is moved right, to clear a side panel)
  constructor(host, opts = {}) {
    this.host = host;
    this.lat = opts.lat ?? 0; this.lon = opts.lon ?? 0; this.zoom = opts.zoom ?? 1;
    this.minZoom = opts.minZoom ?? 1; this.maxZoom = opts.maxZoom ?? 8; this.offsetX = opts.offsetX ?? 0;
    this.home = { lat: this.lat, lon: this.lon, zoom: this.zoom };
    this.tex = {}; this.shapes = []; this.moving = false; this.dirty = true;
    this.reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.sky = Object.assign(document.createElement('canvas'), { className: 'globe__sky' });
    this.raster = Object.assign(document.createElement('canvas'), { className: 'globe__raster' });
    this.over = Object.assign(document.createElement('canvas'), { className: 'globe__over', tabIndex: 0 });
    this.over.setAttribute('aria-label', 'Globe. Drag to turn, scroll to zoom, arrow keys to turn, plus and minus to zoom.');
    host.append(this.sky, this.raster, this.over);
    new ResizeObserver(() => { this.dirty = true; }).observe(host);
    this.measure();
    this.bind();
    const tick = () => { if (this.dirty && this.tex.global) { this.dirty = false; this.render(); } requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  // pictures: { global, north, south } as ImageData. global is plate carree; north and south are the polar pictures
  // of export/site_assets (layers.json: azimuthal equidistant, pole at centre, edge at 60 degrees).
  // Each picture is also kept at half, quarter... size (mips). Drawing reads the size that matches the screen, so bright
  // details do not sparkle while the globe turns.
  setTextures(p) { for (const k in p) if (p[k]) this.tex[k] = { w: p[k].width, h: p[k].height, mips: mips(new Uint32Array(p[k].data.buffer), p[k].width, p[k].height) }; this.dirty = true; }
  // shapes: [{ id, points: [[lon, lat], ...], center: [lon, lat], label, state: 'idle' | 'hover' | 'chosen' }]
  setShapes(shapes) { this.shapes = shapes; this.dirty = true; }
  get R() { return Math.min(this.w, this.h) * 0.42 * this.zoom; }   // globe radius in CSS px

  // longitude, latitude -> CSS x, y and whether the point is on the near side
  project(lon, lat) {
    const la = lat * RAD, lo = (lon - this.lon) * RAD, p = this.lat * RAD;
    const x = Math.cos(la) * Math.sin(lo), y0 = Math.sin(la), z0 = Math.cos(la) * Math.cos(lo);
    const y = y0 * Math.cos(p) - z0 * Math.sin(p), z = y0 * Math.sin(p) + z0 * Math.cos(p);
    return [this.cx + x * this.R, this.cy - y * this.R, z > 0];
  }
  // CSS x, y -> [lon, lat], or null when the point is off the globe
  unproject(px, py) {
    const x2 = (px - this.cx) / this.R, y2 = (this.cy - py) / this.R, q = x2 * x2 + y2 * y2;
    if (q >= 1) return null;
    const z2 = Math.sqrt(1 - q), p = this.lat * RAD, l = this.lon * RAD;
    const y = y2 * Math.cos(p) + z2 * Math.sin(p), z1 = z2 * Math.cos(p) - y2 * Math.sin(p);
    const x = x2 * Math.cos(l) + z1 * Math.sin(l), z = z1 * Math.cos(l) - x2 * Math.sin(l);
    return [((Math.atan2(x, z) * DEG + 540) % 360) - 180, Math.asin(Math.max(-1, Math.min(1, y))) * DEG];
  }

  measure() {
    const box = this.host.getBoundingClientRect();
    this.w = box.width; this.h = box.height; this.cx = this.w / 2 + this.offsetX / 2; this.cy = this.h / 2;
  }

  render() {
    this.measure();
    if (this.sky.width !== Math.round(this.w) || this.sky.height !== Math.round(this.h)) {   // a few faint stars, always the same ones
      this.sky.width = Math.round(this.w); this.sky.height = Math.round(this.h);
      const k = this.sky.getContext('2d'), rnd = (i) => { const v = Math.sin(i * 127.1 + 311.7) * 43758.5453; return v - Math.floor(v); };
      for (let i = 0; i < 170; i++) { k.fillStyle = `rgba(227,227,227,${0.12 + 0.4 * rnd(i + 500)})`; k.beginPath(); k.arc(rnd(i) * this.w, rnd(i + 200) * this.h, 0.4 + 0.7 * rnd(i + 900), 0, 7); k.fill(); }
    }
    // the picture: fewer pixels while moving, so turning stays smooth
    const s = this.moving ? 0.6 : 1, W = Math.max(2, Math.round(this.w * s)), H = Math.max(2, Math.round(this.h * s));
    if (this.raster.width !== W || this.raster.height !== H) { this.raster.width = W; this.raster.height = H; this.img = null; }
    const g = this.raster.getContext('2d');
    if (!this.img) { this.img = g.createImageData(W, H); this.out = new Uint32Array(this.img.data.buffer); }
    const out = this.out; out.fill(0);
    const R = this.R * s, cx = this.cx * s, cy = this.cy * s;
    const sp = Math.sin(this.lat * RAD), cp = Math.cos(this.lat * RAD), sl = Math.sin(this.lon * RAD), cl = Math.cos(this.lon * RAD);
    const PI = Math.PI, EDGE = 30 * RAD, SIN60 = Math.sin(60 * RAD), soft = this.moving ? 0.25 : 0;
    // the size of each picture that gives about one picture pixel per screen pixel (a little softer while moving)
    const pick = (T, span) => T && T.mips[Math.max(0, Math.min(T.mips.length - 1, Math.round(Math.log2(T.w / (span * R)) + soft)))];
    const G = pick(this.tex.global, 2 * PI), N = pick(this.tex.north, 2 * EDGE), S = pick(this.tex.south, 2 * EDGE);
    const LX = -0.46, LY = 0.5, LZ = 0.733;   // direction to the light, unit length
    const j0 = Math.max(0, Math.floor(cy - R)), j1 = Math.min(H, Math.ceil(cy + R));
    for (let j = j0; j < j1; j++) {
      const y2 = (cy - j - 0.5) / R, half = Math.sqrt(Math.max(0, 1 - y2 * y2)) * R;
      const i0 = Math.max(0, Math.ceil(cx - half)), i1 = Math.min(W, Math.floor(cx + half));
      for (let i = i0; i < i1; i++) {
        const x2 = (i + 0.5 - cx) / R, z2 = Math.sqrt(Math.max(0, 1 - x2 * x2 - y2 * y2));
        const y = y2 * cp + z2 * sp, z1 = z2 * cp - y2 * sp, x = x2 * cl + z1 * sl, z = z1 * cl - x2 * sl;
        let c;
        const polar = y > SIN60 ? N : y < -SIN60 ? S : null;
        if (polar) {   // near a pole: the polar picture is sharper there
          const r = Math.acos(Math.min(1, Math.abs(y))) / EDGE, k = r / (Math.hypot(x, z) || 1);
          c = smooth(polar, (0.5 + 0.5 * k * x) * polar.w, (y > 0 ? 0.5 + 0.5 * k * z : 0.5 - 0.5 * k * z) * polar.h, false);
        } else {
          c = smooth(G, (Math.atan2(x, z) / PI + 1) * 0.5 * G.w, (0.5 - Math.asin(y) / PI) * G.h, true);
        }
        // light from the upper left, so the globe reads as a lit sphere
        const lit = x2 * LX + y2 * LY + z2 * LZ, sh = Math.min(256, (0.16 + (lit > 0 ? lit : 0) * 1.02) * 256) | 0;
        out[j * W + i] = 0xff000000 | (((c >> 16 & 255) * sh >> 8) << 16) | (((c >> 8 & 255) * sh >> 8) << 8) | ((c & 255) * sh >> 8);
      }
    }
    g.putImageData(this.img, 0, 0);
    const rim = g.createRadialGradient(cx, cy, R * 0.955, cx, cy, R * 1.003);   // a soft edge, so the limb is not jagged
    rim.addColorStop(0, 'rgba(0,0,0,0)'); rim.addColorStop(1, 'rgba(0,0,0,0.9)');
    g.fillStyle = rim; g.beginPath(); g.arc(cx, cy, R + 1, 0, 7); g.fill();
    this.drawShapes();
    this.onview?.();
  }

  drawShapes() {
    const d = Math.min(2, window.devicePixelRatio || 1), cv = this.over, W = Math.round(this.w * d), H = Math.round(this.h * d);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const g = cv.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, this.w, this.h);
    const css = getComputedStyle(document.documentElement), tok = (n) => css.getPropertyValue(n).trim();
    const answer = tok('--answer'), white = tok('--white'), dark = 'rgba(0,0,0,0.65)';
    g.lineJoin = 'round'; g.font = `500 12px ${tok('--f-mono')}`; g.textAlign = 'center'; g.textBaseline = 'middle';
    const order = [...this.shapes].sort((a, b) => (a.state === 'idle' ? 0 : 1) - (b.state === 'idle' ? 0 : 1));
    for (const s of order) {
      const pts = s.points.map(([lon, lat]) => this.project(lon, lat));
      let pen = false, minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9, seen = 0;
      g.beginPath();
      for (let i = 0; i <= pts.length; i++) {
        const [x, y, near] = pts[i % pts.length];
        if (!near) { pen = false; continue; }
        if (pen) g.lineTo(x, y); else g.moveTo(x, y);
        pen = true; seen++;
        minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      }
      const [mx, my, mNear] = this.project(s.center[0], s.center[1]);
      s.screen = mNear ? { x: mx, y: my, r: Math.max(14, Math.max(maxX - minX, maxY - minY) / 2 + 6) } : null;
      if (!seen || !mNear) continue;
      const strong = s.state !== 'idle', w = s.state === 'chosen' ? 2.5 : strong ? 2 : 1.5, col = strong ? white : answer;
      const tiny = Math.max(maxX - minX, maxY - minY) < 14;
      if (!tiny) {
        g.lineWidth = w + 2; g.strokeStyle = dark; g.stroke(); g.lineWidth = w; g.strokeStyle = col; g.stroke();
      } else {   // too small to see as a shape: a dot; hover and choice add a ring
        g.fillStyle = dark; g.beginPath(); g.arc(mx, my, 5, 0, 7); g.fill();
        g.fillStyle = col; g.beginPath(); g.arc(mx, my, 3.5, 0, 7); g.fill();
        if (strong) { g.lineWidth = 1.5; g.strokeStyle = col; g.beginPath(); g.arc(mx, my, 10, 0, 7); g.stroke(); }
      }
      if (s.label != null && (strong || !tiny)) {   // the number chip, up and to the right of the shape (not on tiny idle shapes: they would pile up)
        const tx = Math.max(maxX, mx + 9) + 12, ty = Math.min(minY, my - 9) - 2, tw = g.measureText(s.label).width + 12;
        g.fillStyle = s.state === 'chosen' ? tok('--primary') : tok('--surface-1');
        g.beginPath(); g.roundRect(tx - tw / 2, ty - 10, tw, 20, 3); g.fill();
        if (s.state !== 'chosen') { g.lineWidth = 1; g.strokeStyle = strong ? white : tok('--outline-2'); g.stroke(); }
        g.fillStyle = s.state === 'chosen' ? tok('--on-primary') : tok('--on-surface'); g.fillText(s.label, tx, ty + 0.5);
      }
    }
  }

  // the shape under a CSS point, or null
  hit(px, py) {
    let best = null, bd = 1e9;
    for (const s of this.shapes) { if (!s.screen || s.nohit) continue; const d = Math.hypot(px - s.screen.x, py - s.screen.y); if (d <= s.screen.r && d < bd) { bd = d; best = s; } }
    return best;
  }

  // turn and zoom to a view; a camera move of --t-move, or a jump with reduced motion
  flyTo(lat, lon, zoom = this.zoom) {
    zoom = Math.max(this.minZoom, Math.min(this.maxZoom, zoom)); lat = Math.max(-89.5, Math.min(89.5, lat));
    cancelAnimationFrame(this.fly);
    if (this.reduced) { Object.assign(this, { lat, lon, zoom, moving: false, dirty: true }); return; }
    const a = { lat: this.lat, lon: this.lon, zoom: this.zoom }, dl = ((lon - a.lon + 540) % 360) - 180, t0 = performance.now();
    const ms = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--t-move')) || 700;
    const step = (now) => {
      const t = Math.min(1, (now - t0) / ms), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.lat = a.lat + (lat - a.lat) * e; this.lon = a.lon + dl * e; this.zoom = Math.exp(Math.log(a.zoom) + (Math.log(zoom) - Math.log(a.zoom)) * e);
      this.moving = t < 1; this.dirty = true;
      if (t < 1) this.fly = requestAnimationFrame(step);
    };
    this.fly = requestAnimationFrame(step);
  }
  zoomBy(f) { this.flyTo(this.lat, this.lon, this.zoom * f); }
  reset() { this.flyTo(this.home.lat, this.home.lon, this.home.zoom); }

  bind() {
    const cv = this.over; let down = null, idle;
    const settle = () => { clearTimeout(idle); idle = setTimeout(() => { this.moving = false; this.dirty = true; }, 140); };
    const at = (e) => { const b = cv.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
    cv.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, moved: 0 }; cv.setPointerCapture(e.pointerId); cancelAnimationFrame(this.fly); });
    cv.addEventListener('pointermove', (e) => {
      const [x, y] = at(e);
      if (down) {
        const dx = e.clientX - down.x, dy = e.clientY - down.y; down.x = e.clientX; down.y = e.clientY; down.moved += Math.abs(dx) + Math.abs(dy);
        const k = DEG / this.R;
        this.lon -= dx * k / Math.max(0.2, Math.cos(this.lat * RAD)); this.lat = Math.max(-89.5, Math.min(89.5, this.lat + dy * k));
        this.moving = true; this.dirty = true; settle();
      } else this.onhover?.(this.hit(x, y), this.unproject(x, y));
    });
    cv.addEventListener('pointerup', (e) => { const [x, y] = at(e); if (down && down.moved < 5) this.onpick?.(this.hit(x, y), this.unproject(x, y)); down = null; });
    cv.addEventListener('pointercancel', () => { down = null; });
    cv.addEventListener('pointerleave', () => this.onhover?.(null, null));
    cv.addEventListener('wheel', (e) => {
      e.preventDefault(); cancelAnimationFrame(this.fly);
      this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.zoom * Math.exp(-e.deltaY * 0.0015)));
      this.moving = true; this.dirty = true; settle();
    }, { passive: false });
    cv.addEventListener('keydown', (e) => {
      const step = 12 / this.zoom, k = e.key;
      if (k === 'ArrowLeft') this.flyTo(this.lat, this.lon - step); else if (k === 'ArrowRight') this.flyTo(this.lat, this.lon + step);
      else if (k === 'ArrowUp') this.flyTo(this.lat + step, this.lon); else if (k === 'ArrowDown') this.flyTo(this.lat - step, this.lon);
      else if (k === '+' || k === '=') this.zoomBy(1.5); else if (k === '-') this.zoomBy(1 / 1.5); else return;
      e.preventDefault();
    });
  }
}

// A picture at full, half, quarter... size: each step is the average of 2 x 2 pixels of the one before.
function mips(px, w, h) {
  const out = [{ px, w, h }];
  while (w >= 512 && h >= 256 && out.length < 5) {
    const W = w >> 1, H = h >> 1, o = new Uint32Array(W * H);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const i = 2 * y * w + 2 * x, a = px[i], b = px[i + 1], c = px[i + w], d = px[i + w + 1];
      o[y * W + x] = 0xff000000 | (((a >> 16 & 255) + (b >> 16 & 255) + (c >> 16 & 255) + (d >> 16 & 255) + 2 >> 2) << 16)
        | (((a >> 8 & 255) + (b >> 8 & 255) + (c >> 8 & 255) + (d >> 8 & 255) + 2 >> 2) << 8) | ((a & 255) + (b & 255) + (c & 255) + (d & 255) + 2 >> 2);
    }
    out.push({ px: o, w: W, h: H }); px = o; w = W; h = H;
  }
  return out;
}
// The colour at a point between pixels: a blend of the four pixels around it. wrap: the picture joins left to right.
function smooth(T, u, v, wrap) {
  const w = T.w, h = T.h, px = T.px; u -= 0.5; v -= 0.5;
  let x0 = Math.floor(u), y0 = Math.floor(v); const fx = (u - x0) * 256 | 0, fy = (v - y0) * 256 | 0;
  let x1 = x0 + 1, y1 = y0 + 1;
  if (wrap) { x0 = (x0 % w + w) % w; x1 = (x1 % w + w) % w; } else { x0 = x0 < 0 ? 0 : x0 >= w ? w - 1 : x0; x1 = x1 < 0 ? 0 : x1 >= w ? w - 1 : x1; }
  y0 = y0 < 0 ? 0 : y0 >= h ? h - 1 : y0; y1 = y1 < 0 ? 0 : y1 >= h ? h - 1 : y1;
  const a = px[y0 * w + x0], b = px[y0 * w + x1], c = px[y1 * w + x0], d = px[y1 * w + x1];
  const wa = (256 - fx) * (256 - fy), wb = fx * (256 - fy), wc = (256 - fx) * fy, wd = fx * fy;
  return (((a >> 16 & 255) * wa + (b >> 16 & 255) * wb + (c >> 16 & 255) * wc + (d >> 16 & 255) * wd) >> 16 << 16)
    | (((a >> 8 & 255) * wa + (b >> 8 & 255) * wb + (c >> 8 & 255) * wc + (d >> 8 & 255) * wd) >> 16 << 8)
    | (((a & 255) * wa + (b & 255) * wb + (c & 255) * wc + (d & 255) * wd) >> 16);
}

// Helpers for building globe pictures.
export const loadImage = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error('cannot load ' + src)); i.src = src; });
// An image as pixels, with a CSS filter and an optional [r, g, b] tint multiplied in.
export function pixels(img, w, h, filter, tint) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d', { willReadFrequently: true }); if (filter) g.filter = filter;
  g.drawImage(img, 0, 0, w, h);
  const out = g.getImageData(0, 0, w, h);
  if (tint) { const d = out.data, [r, gr, b] = tint; for (let i = 0; i < d.length; i += 4) { d[i] = d[i] * r / 255; d[i + 1] = d[i + 1] * gr / 255; d[i + 2] = d[i + 2] * b / 255; } }
  return out;
}
// A circle of radius_km around a point, as [lon, lat] points (for disc targets).
export function circlePoints(lon0, lat0, radiusKm, bodyRadiusKm, steps = 96) {
  const d = radiusKm / bodyRadiusKm, la0 = lat0 * RAD, lo0 = lon0 * RAD, out = [];
  for (let i = 0; i < steps; i++) {
    const b = i / steps * 2 * Math.PI;
    const la = Math.asin(Math.sin(la0) * Math.cos(d) + Math.cos(la0) * Math.sin(d) * Math.cos(b));
    const lo = lo0 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la0), Math.cos(d) - Math.sin(la0) * Math.sin(la));
    out.push([lo * DEG, la * DEG]);
  }
  return out;
}
