/* Scenes for the Analog Finder explainer.
   Each step: { ch, title, text, dur, note?, draw(g, t) }, t runs 0..1 and then holds at 1.
   Real data comes from DATA (build/explainer_data.py). Steps with `note` use invented numbers. */
const TEMP = [[0, [70, 52, 160]], [.35, [176, 54, 140]], [.7, [240, 122, 60]], [1, [255, 215, 90]]];
const COOL = [[0, [38, 60, 96]], [.5, [57, 135, 229]], [1, [170, 222, 255]]];
const ILLUS = "Illustration · invented numbers";
const fmt = n => Math.round(n).toLocaleString("en-US");

function boxes(g, n, o = {}) {
  const pad = o.pad || .05, top = o.top == null ? .12 : o.top, bot = o.bot == null ? .94 : o.bot, out = [];
  if (!g.narrow) { const w = (1 - pad * (n + 1)) / n; for (let i = 0; i < n; i++) out.push({ x: g.W * (pad + i * (w + pad)), y: g.H * top, w: g.W * w, h: g.H * (bot - top) }); }
  else { const gp = .035, h = (bot - top - gp * (n - 1)) / n; for (let i = 0; i < n; i++) out.push({ x: g.W * .06, y: g.H * (top + i * (h + gp)), w: g.W * .88, h: g.H * h }); }
  return out;
}
function head(g, s, a) { g.text(s, g.X(.05), g.Y(g.narrow && g.note ? .108 : .065), { size: 1.15, weight: 600, display: true, alpha: a == null ? 1 : a }); }
function invNorm(p) { const x = 2 * p - 1, a = .147, l = Math.log(1 - x * x), q = 2 / (Math.PI * a) + l / 2; return Math.SQRT2 * Math.sign(x) * Math.sqrt(Math.sqrt(q * q - l / a) - q); }

/* ---------------------------------------------------------------- 0 question */
function sQuestion(g, t) {
  const { C } = g, n = g.narrow, m = Math.min(g.W, g.H);
  const mo = n ? { x: g.X(.3), y: g.Y(.26), r: m * .2 } : { x: g.X(.2), y: g.Y(.42), r: m * .24 };
  const ma = n ? { x: g.X(.74), y: g.Y(.2), r: m * .13 } : { x: g.X(.13), y: g.Y(.82), r: m * .11 };
  const ea = n ? { x: g.X(.5), y: g.Y(.7), r: m * .3 } : { x: g.X(.7), y: g.Y(.53), r: m * .38 };
  const a0 = g.seg(t, 0, .2);
  [[mo, C.moon, "Moon"], [ma, C.mars, "Mars"], [ea, C.earth, "Earth"]].forEach(([b, col, name]) => {
    g.dot(b.x, b.y, b.r, C.panel, a0); g.ring(b.x, b.y, b.r, col, 2.5, a0);
    g.text(name, b.x, b.y - b.r - g.fs(1), { align: "center", color: C.mute, alpha: a0 });
  });
  for (let i = 0; i < 9; i++) { const a = g.rnd(i) * 6.28, d = Math.sqrt(g.rnd(i + 20)) * mo.r * .8; g.ring(mo.x + Math.cos(a) * d, mo.y + Math.sin(a) * d, mo.r * (.05 + .09 * g.rnd(i + 40)), C.line, 1.2, a0); }
  const tx = mo.x + mo.r * .1, ty = mo.y + mo.r * .62, a1 = g.seg(t, .15, .35), sq = mo.r * .16;
  g.rect(tx - sq / 2, ty - sq / 2, sq, sq, { fill: C.hi, alpha: a1, r: 2 });
  g.text("a landing region", tx, ty + sq * 1.3, { color: C.hi, alpha: a1, size: .9, align: "center" });
  const a2 = g.seg(t, .35, .6), ex = ea.x - ea.r * .95, ey = ea.y;
  if (a2 > 0) g.arrow(tx + sq, ty, g.lerp(tx + sq, ex, a2), g.lerp(ty, ey, a2), { color: C.hi, w: 2, dash: [6, 6], alpha: .9 });
  const best = [7, 23, 41];
  for (let i = 0; i < 60; i++) {
    const a = g.rnd(i + 100) * 6.28, d = Math.sqrt(g.rnd(i + 200)) * ea.r * .9, x = ea.x + Math.cos(a) * d, y = ea.y + Math.sin(a) * d;
    const ai = g.seg(t, .5 + i * .004, .62 + i * .004), hot = best.includes(i) ? g.seg(t, .8, .95) : 0;
    g.dot(x, y, 2.4 + hot * 4, hot > 0 ? C.hi : C.earth, ai * (hot > 0 ? 1 : .55));
    if (hot > .5) g.ring(x, y, 9 + 5 * Math.sin(t * 20 + i), C.hi, 1.5, .6);
  }
  g.text("Which of these places is most like it?", ea.x, ea.y + ea.r + g.fs(1.3), { align: "center", size: 1.05, weight: 600, alpha: g.seg(t, .82, 1) });
}

/* ---------------------------------------------------------------- 1 grid */
function sSizes(g, t) {
  const { C } = g, items = [["Elevation", "a point every 0.5 km"], ["Temperature", "a square every 5 km"], ["Lunar chemistry", "one block per 60 km"], ["Rock map", "hand-drawn shapes"]];
  const cols = g.narrow ? 2 : 4, rows = g.narrow ? 2 : 1, gw = g.W * .9 / cols, gh = g.H * (g.narrow ? .42 : .7);
  head(g, "The raw data comes in four different shapes");
  items.forEach((it, i) => {
    const a = g.seg(t, i * .17, i * .17 + .25), cx = g.W * .05 + gw * (i % cols) + gw / 2, top = g.H * .14 + gh * Math.floor(i / cols);
    const s = Math.min(gw * .72, gh * .62), x0 = cx - s / 2, y0 = top + gh * .06;
    g.rect(x0, y0, s, s, { stroke: C.line, r: 6, alpha: a });
    if (i === 0) for (let r = 0; r < 14; r++) for (let c = 0; c < 14; c++) g.dot(x0 + s * (c + .5) / 14, y0 + s * (r + .5) / 14, 1.3, C.earth, a * (.35 + .65 * g.rnd(r * 14 + c)));
    if (i === 1) for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) g.rect(x0 + s * c / 5 + 2, y0 + s * r / 5 + 2, s / 5 - 4, s / 5 - 4, { fill: C.mars, alpha: a * (.25 + .7 * g.rnd(r * 5 + c + 9)), r: 2 });
    if (i === 2) g.rect(x0 + 4, y0 + 4, s - 8, s - 8, { fill: C.moon, alpha: a * .7, r: 4 });
    if (i === 3) {
      const P = (u, v) => [x0 + s * u, y0 + s * v];
      g.poly([P(.05, .08), P(.6, .05), P(.45, .5), P(.08, .62)], { fill: C.hi, alpha: a * .55, close: true });
      g.poly([P(.6, .05), P(.95, .1), P(.92, .7), P(.45, .5)], { fill: C.earth, alpha: a * .5, close: true });
      g.poly([P(.08, .62), P(.45, .5), P(.92, .7), P(.9, .95), P(.1, .93)], { fill: C.mars, alpha: a * .5, close: true });
    }
    g.text(it[0], cx, y0 + s + g.fs(1.2), { align: "center", weight: 600, alpha: a });
    g.text(it[1], cx, y0 + s + g.fs(2.5), { align: "center", color: C.mute, size: .88, alpha: a });
  });
}
function proj(lat, lon, tilt) {
  const la = lat * Math.PI / 180, lo = lon * Math.PI / 180, f = tilt * Math.PI / 180;
  return { x: Math.cos(la) * Math.sin(lo), y: -(Math.cos(f) * Math.sin(la) - Math.sin(f) * Math.cos(la) * Math.cos(lo)), z: Math.sin(f) * Math.sin(la) + Math.cos(f) * Math.cos(la) * Math.cos(lo) };
}
function arc(g, cx, cy, R, pts, o) { let seg = []; pts.forEach(p => { const q = proj(p[0], p[1], 32); if (q.z > 0) seg.push([cx + q.x * R, cy + q.y * R]); else { if (seg.length > 1) g.poly(seg, o); seg = []; } }); if (seg.length > 1) g.poly(seg, o); }
function cellPoly(g, cx, cy, R, la0, la1, lo0, lo1) {
  const pts = [];
  for (let k = 0; k <= 8; k++) pts.push([la0, lo0 + (lo1 - lo0) * k / 8]);
  for (let k = 0; k <= 8; k++) pts.push([la0 + (la1 - la0) * k / 8, lo1]);
  for (let k = 0; k <= 8; k++) pts.push([la1, lo1 - (lo1 - lo0) * k / 8]);
  for (let k = 0; k <= 8; k++) pts.push([la1 - (la1 - la0) * k / 8, lo0]);
  return pts.map(p => { const q = proj(p[0], p[1], 32); return [cx + q.x * R, cy + q.y * R]; });
}
function sShrink(g, t) {
  const { C } = g, n = g.narrow, R = Math.min(g.W, g.H) * (n ? .3 : .36), cx = n ? g.X(.5) : g.X(.3), cy = n ? g.Y(.36) : g.Y(.54);
  const a1 = 1 - g.seg(t, .62, .8), a2 = g.seg(t, .7, .9), a0 = g.seg(t, 0, .2);
  head(g, a2 > .5 ? "Equal-area cells: every cell covers the same ground" : "A latitude–longitude grid shrinks toward the poles");
  g.dot(cx, cy, R, C.panel, a0); g.ring(cx, cy, R, C.line, 1.5, a0);
  const st = { stroke: C.mute, w: 1, alpha: .55 * a0 * a1 };
  if (a1 > 0) {
    for (let la = -75; la <= 75; la += 15) { const p = []; for (let lo = -180; lo <= 180; lo += 5) p.push([la, lo]); arc(g, cx, cy, R, p, st); }
    for (let lo = -180; lo < 180; lo += 15) { const p = []; for (let la = -90; la <= 90; la += 5) p.push([la, lo]); arc(g, cx, cy, R, p, st); }
    [[0, 15], [45, 60], [75, 90]].forEach((b, i) => g.poly(cellPoly(g, cx, cy, R, b[0], b[1], -7.5, 7.5), { fill: C.hi, close: true, alpha: g.seg(t, .2 + i * .08, .35 + i * .08) * a1 * .9 }));
  }
  if (a2 > 0) {
    const N = 7, st2 = { stroke: C.moon, w: 1, alpha: .75 * a2 };
    for (let k = -N; k < N; k++) {
      const la0 = Math.asin(k / N) * 180 / Math.PI, la1 = Math.asin((k + 1) / N) * 180 / Math.PI, mid = (la0 + la1) / 2;
      const m = Math.max(4, Math.round(26 * Math.cos(mid * Math.PI / 180)));
      const p = []; for (let lo = -180; lo <= 180; lo += 5) p.push([la0, lo]); arc(g, cx, cy, R, p, st2);
      for (let j = 0; j < m; j++) { const lo = -180 + 360 * (j + (k % 2 ? .5 : 0)) / m; arc(g, cx, cy, R, [[la0, lo], [mid, lo], [la1, lo]], st2); }
    }
    [[0, 1, 3], [3, 4, 2], [6, 7, 1]].forEach((b, i) => {
      const la0 = Math.asin(b[0] / N) * 180 / Math.PI, la1 = Math.asin(b[1] / N) * 180 / Math.PI, mid = (la0 + la1) / 2, m = Math.max(4, Math.round(26 * Math.cos(mid * Math.PI / 180))), w = 360 / m;
      g.poly(cellPoly(g, cx, cy, R, la0, la1, -w / 2, w / 2), { fill: C.hi, close: true, alpha: a2 * .9 });
    });
  }
  const bx = n ? g.X(.14) : g.X(.62), by = n ? g.Y(.74) : g.Y(.3), u = Math.min(g.W, g.H) * (n ? .13 : .17);
  const areas = [1, .614, .131], names = ["at the equator", "at 50°", "near the pole"];
  names.forEach((nm, i) => {
    const a = g.seg(t, .25 + i * .08, .45 + i * .08), sOld = u * Math.sqrt(areas[i]), s = g.lerp(sOld, u * .62, a2);
    const x = n ? bx + i * g.W * .26 : bx, y = n ? by : by + i * u * 1.05;
    g.rect(x, y + (u - s) / 2, s, s, { fill: C.hi, alpha: a * .9, r: 2 });
    if (n) g.text(nm, x, y + u + g.fs(.9), { color: C.mute, size: .82, alpha: a });
    else g.text(nm, x + u * 1.2, y + u / 2, { color: C.mute, alpha: a });
  });
  const lx = n ? g.X(.5) : bx, ly = n ? g.Y(.95) : by + u * 3.4;
  g.text("7.6× smaller than at the equator", lx, ly, { color: C.bad, weight: 600, align: n ? "center" : "left", alpha: g.seg(t, .45, .6) * a1 });
  g.text("same area everywhere", lx, ly, { color: C.good, weight: 600, align: n ? "center" : "left", alpha: a2 });
}
function sRuler(g, t) {
  const { C } = g, n = g.narrow, bodies = [["Earth", C.earth, 1, DATA.num.cells.earth, 6.4], ["Mars", C.mars, .533, DATA.num.cells.mars, 6.8], ["Moon", C.moon, .273, DATA.num.cells.moon, 6.9]];
  head(g, "One ruler for three worlds");
  const R0 = Math.min(g.W * (n ? .3 : .19), g.H * (n ? .2 : .3)), pitch = Math.max(5, R0 / 14);
  let x = n ? g.X(.5) : g.X(.06) + R0, y = n ? g.Y(.14) + R0 : g.Y(.5);
  bodies.forEach((b, i) => {
    const R = R0 * b[2], a = g.seg(t, i * .15, i * .15 + .3), cy = n ? y : g.Y(.5), cx = n ? g.X(.34) : x;
    g.ctx.save(); g.ctx.beginPath(); g.ctx.arc(cx, cy, R, 0, 6.2832); g.ctx.clip();
    g.rect(cx - R, cy - R, 2 * R, 2 * R, { fill: C.panel, alpha: a });
    for (let k = -R; k <= R; k += pitch) { g.line(cx + k, cy - R, cx + k, cy + R, { color: b[1], w: 1, alpha: a * .55 }); g.line(cx - R, cy + k, cx + R, cy + k, { color: b[1], w: 1, alpha: a * .55 }); }
    g.ctx.restore(); g.ring(cx, cy, R, b[1], 2.5, a);
    const tx = n ? g.X(.62) : cx, ty = n ? cy : g.Y(.5) + R0 + g.fs(1.6), al = n ? "left" : "center";
    g.text(b[0], tx, ty - (n ? g.fs(1.3) : 0), { align: al, weight: 600, alpha: a });
    g.text(fmt(b[3] * g.seg(t, i * .15 + .1, i * .15 + .55)) + " cells", tx, ty + (n ? 0 : g.fs(1.4)), { align: al, color: C.mute, alpha: a, size: .92 });
    g.text("one cell ≈ " + b[4] + " km", tx, ty + (n ? g.fs(1.3) : g.fs(2.7)), { align: al, color: C.hi, alpha: g.seg(t, .7, .9), size: .92 });
    if (n) y += Math.max(R, g.fs(2.2)) + (bodies[i + 1] ? R0 * bodies[i + 1][2] : 0) + g.H * .07; else x += R + (bodies[i + 1] ? R0 * bodies[i + 1][2] : 0) + g.W * .1;
  });
}
function sFill(g, t) {
  const { C } = g, bx = boxes(g, 3, { top: .16 });
  head(g, "Three ways a cell gets its value");
  const titles = [["Finer data", "average it"], ["Coarser data", "copy it"], ["Categories", "the majority wins"]];
  bx.forEach((b, i) => {
    const a = g.seg(t, i * .12, i * .12 + .2), s = Math.min(b.w * .62, b.h * (g.narrow ? .62 : .5)), x0 = b.x + (g.narrow ? b.w * .04 : (b.w - s) / 2), y0 = b.y + (g.narrow ? (b.h - s) / 2 : b.h * .06);
    const tx = g.narrow ? x0 + s + b.w * .08 : b.x + b.w / 2, ty = g.narrow ? y0 + s * .4 : y0 + s + g.fs(1.5), al = g.narrow ? "left" : "center";
    g.text(titles[i][0], tx, ty, { align: al, weight: 600, alpha: a }); g.text(titles[i][1], tx, ty + g.fs(1.35), { align: al, color: C.mute, alpha: a, size: .92 });
    if (i === 0) {
      const m = g.seg(t, .3, .6);
      g.rect(x0, y0, s, s, { fill: g.ramp(.55, TEMP), alpha: m * a, r: 4 }); g.rect(x0, y0, s, s, { stroke: C.ink, r: 4, alpha: a });
      for (let k = 0; k < 36; k++) { const u = g.rnd(k) * .84 + .08, v = g.rnd(k + 50) * .84 + .08; g.dot(g.lerp(x0 + s * u, x0 + s / 2, m), g.lerp(y0 + s * v, y0 + s / 2, m), 3.2, g.ramp(.2 + .7 * g.rnd(k + 90), TEMP), a * (1 - m * .9)); }
    }
    if (i === 1) {
      const col = g.ramp(.78, TEMP);
      for (let k = 0; k < 4; k++) { const f = g.seg(t, .45 + k * .08, .6 + k * .08); g.rect(x0 + (k % 2) * s / 2 + 2, y0 + Math.floor(k / 2) * s / 2 + 2, s / 2 - 4, s / 2 - 4, { fill: col, alpha: a * f, r: 3 }); g.rect(x0 + (k % 2) * s / 2 + 2, y0 + Math.floor(k / 2) * s / 2 + 2, s / 2 - 4, s / 2 - 4, { stroke: C.ink, alpha: a, r: 3 }); }
      g.rect(x0 - 5, y0 - 5, s + 10, s + 10, { stroke: col, w: 2.5, r: 6, alpha: a * (1 - g.seg(t, .75, .95) * .6) });
    }
    if (i === 2) {
      const m = g.seg(t, .65, .9);
      g.poly([[x0, y0], [x0 + s * .78, y0], [x0 + s * .5, y0 + s], [x0, y0 + s]], { fill: C.hi, close: true, alpha: a * .8 });
      g.poly([[x0 + s * .78, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0 + s * .5, y0 + s]], { fill: C.earth, close: true, alpha: a * .8 * (1 - m) });
      g.poly([[x0 + s * .78, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0 + s * .5, y0 + s]], { fill: C.hi, close: true, alpha: a * .8 * m });
      g.rect(x0, y0, s, s, { stroke: C.ink, r: 4, alpha: a });
      g.text("64%", x0 + s * .3, y0 + s / 2, { align: "center", weight: 600, color: C.bg, alpha: a }); g.text("36%", x0 + s * .82, y0 + s * .5, { align: "center", weight: 600, color: C.bg, alpha: a * (1 - m) });
    }
  });
}

/* ---------------------------------------------------------------- 2 variables */
const prof = x => .5 + .12 * Math.sin(6.3 * x + 1) + .06 * Math.sin(15 * x) + .025 * Math.sin(41 * x + 2) - .24 * Math.exp(-Math.pow((x - .62) / .075, 2)) + .06 * Math.exp(-Math.pow((x - .5) / .03, 2)) + .06 * Math.exp(-Math.pow((x - .74) / .03, 2));
function terrain(g) {
  const PX = x => g.X(.05 + .9 * x), PY = h => g.Y(.86 - .62 * h), pts = [];
  for (let i = 0; i <= 200; i++) pts.push([PX(i / 200), PY(prof(i / 200))]);
  g.poly(pts.concat([[PX(1), g.Y(.93)], [PX(0), g.Y(.93)]]), { fill: g.C.panel, close: true }); g.poly(pts, { stroke: g.C.ink, w: 2 });
  return { PX, PY };
}
function sSlope(g, t) {
  const { C } = g, { PX, PY } = terrain(g), a = g.seg(t, 0, .45), x = g.lerp(.1, .3, a), d = (prof(x + .004) - prof(x - .004)) / .008;
  const ang = Math.atan(d * .62 * g.H / (.9 * g.W)), L = g.W * .09, px = PX(x), py = PY(prof(x));
  head(g, t < .5 ? "Slope: how steep is the ground here?" : "Roughness: how bumpy is it inside a window?");
  const s1 = 1 - g.seg(t, .45, .55);
  if (s1 > 0) { g.line(px - L * Math.cos(ang), py + L * Math.sin(ang), px + L * Math.cos(ang), py - L * Math.sin(ang), { color: C.hi, w: 3, alpha: s1 }); g.text("steepness " + Math.abs(ang * 180 / Math.PI).toFixed(0) + "°", px, py - g.fs(2.4), { align: "center", color: C.hi, weight: 600, alpha: s1 }); }
  const s2 = g.seg(t, .5, .6), w = g.lerp(.035, .2, g.seg(t, .6, .95));
  if (s2 > 0) {
    let lo = 9, hi = -9; for (let k = 0; k <= 60; k++) { const h = prof(x - w + 2 * w * k / 60); lo = Math.min(lo, h); hi = Math.max(hi, h); }
    g.rect(PX(x - w), PY(hi), PX(x + w) - PX(x - w), PY(lo) - PY(hi), { fill: C.hi, alpha: .18 * s2 });
    g.line(PX(x - w), PY(hi), PX(x + w), PY(hi), { color: C.hi, dash: [5, 5], alpha: s2 }); g.line(PX(x - w), PY(lo), PX(x + w), PY(lo), { color: C.hi, dash: [5, 5], alpha: s2 });
    g.text("window " + Math.round(g.lerp(5, 42, g.seg(t, .6, .95))) + " km", PX(x), PY(hi) - g.fs(1.2), { align: "center", color: C.hi, weight: 600, alpha: s2 });
    g.text("the wider the window, the bigger the bumps it sees", g.X(.5), g.Y(.16), { align: "center", color: C.mute, alpha: g.seg(t, .8, 1) });
  }
  g.dot(px, py, 6, C.hi);
}
function sBowl(g, t) {
  const { C } = g, { PX, PY } = terrain(g), x = .62, w = .17, px = PX(x), py = PY(prof(x));
  let mean = 0; for (let k = 0; k <= 60; k++) mean += prof(x - w + 2 * w * k / 60) / 61;
  head(g, t < .5 ? "Landform position: in a bowl or on a ridge?" : "Sky view: how much open sky can you see?");
  const a = g.seg(t, 0, .25) * (1 - g.seg(t, .48, .58));
  g.line(PX(x - w), PY(mean), PX(x + w), PY(mean), { color: C.earth, dash: [6, 5], w: 2, alpha: a }); g.text("average height nearby", PX(x + w) + 6, PY(mean), { color: C.earth, alpha: a, size: .9 });
  if (a > 0) g.arrow(px, PY(mean), px, g.lerp(PY(mean), py - 8, g.seg(t, .2, .42)), { color: C.hi, w: 2.5, alpha: a });
  g.text("below its surroundings: a bowl", px, py + g.fs(1.6), { align: "center", color: C.hi, weight: 600, alpha: g.seg(t, .3, .45) * (1 - g.seg(t, .48, .58)) });
  const b = g.seg(t, .55, .9);
  if (b > 0) {
    let aL = -9, aR = -9;
    for (let k = 1; k <= 120; k++) { const dx = .3 * k / 120, hl = (PY(prof(x)) - PY(prof(x - dx))) / (PX(x) - PX(x - dx)), hr = (PY(prof(x)) - PY(prof(x + dx))) / (PX(x + dx) - PX(x)); aL = Math.max(aL, Math.atan(hl)); aR = Math.max(aR, Math.atan(hr)); }
    const L = g.H * .55, pts = [[px, py]];
    for (let k = 0; k <= 30; k++) { const an = Math.PI - aL - (Math.PI - aL - aR) * (k / 30) * b; pts.push([px + L * Math.cos(an), py - L * Math.sin(an)]); }
    g.poly(pts, { fill: C.hi, close: true, alpha: .22 }); g.line(px, py, px - L * Math.cos(aL), py - L * Math.sin(aL), { color: C.hi, w: 2 }); if (b > .98) g.line(px, py, px + L * Math.cos(aR), py - L * Math.sin(aR), { color: C.hi, w: 2 });
    g.text("the walls hide part of the sky", px, g.Y(.17), { align: "center", color: C.hi, weight: 600, alpha: g.seg(t, .85, 1) });
  }
  g.dot(px, py, 6, C.hi);
}
function sThermal(g, t) {
  const { C } = g, bx = boxes(g, 2, { top: .16, bot: .9 }), A = bx[0], B = bx[1];
  head(g, "Temperature and rock chemistry");
  const T = h => 256 + 36 * Math.exp(-Math.pow((h - 14) / 4.3, 2)) + 7 * Math.exp(-Math.pow((h - 21) / 4.5, 2));
  const X = h => A.x + A.w * (.1 + .85 * h / 24), Y = v => A.y + A.h * (.86 - .78 * (v - 246) / 54), n = Math.round(96 * g.seg(t, 0, .4)), pts = [];
  g.line(X(0), Y(246), X(24), Y(246), { color: C.line }); ["midnight", "noon", "midnight"].forEach((s, i) => g.text(s, X(i * 12), Y(246) + g.fs(1.1), { align: "center", color: C.mute, size: .82 }));
  for (let k = 0; k <= n; k++) pts.push([X(k / 4), Y(T(k / 4))]);
  if (pts.length > 1) g.poly(pts, { stroke: C.mars, w: 2.5 });
  const a1 = g.seg(t, .4, .55), a2 = g.seg(t, .55, .75), lv = 268;
  g.line(X(0), Y(lv), X(24), Y(lv), { color: C.hi, dash: [6, 5], alpha: a1 }); g.text("level (average)", X(.4), Y(lv) - g.fs(.9), { color: C.hi, alpha: a1, size: .9 });
  g.line(X(23.3), Y(292), X(23.3), Y(256.5), { color: C.ink, w: 2, alpha: a2 }); g.line(X(22.8), Y(292), X(23.8), Y(292), { color: C.ink, w: 2, alpha: a2 }); g.line(X(22.8), Y(256.5), X(23.8), Y(256.5), { color: C.ink, w: 2, alpha: a2 });
  g.text("day–night swing", X(22.6), Y(297), { align: "right", alpha: a2, size: .9, weight: 600 });
  const rows = [["granite-like", 72, 3], ["basalt-like", 50, 10]];
  rows.forEach((r, i) => {
    const a = g.seg(t, .6 + i * .1, .8 + i * .1), y = B.y + B.h * (.2 + i * .42), x0 = B.x + B.w * .06, w = B.w * .86;
    g.text(r[0], x0, y, { weight: 600, alpha: a });
    g.rect(x0, y + g.fs(1), w * r[1] / 100 * a, g.fs(1.1), { fill: C.earth, r: 3, alpha: a }); g.text("silica " + r[1] + "%", x0 + w * r[1] / 100 + 6, y + g.fs(1.55), { color: C.mute, size: .85, alpha: a });
    g.rect(x0, y + g.fs(2.5), w * r[2] / 100 * a * 2.5, g.fs(1.1), { fill: C.mars, r: 3, alpha: a }); g.text("iron oxide " + r[2] + "%", x0 + w * r[2] / 100 * 2.5 + 6, y + g.fs(3.05), { color: C.mute, size: .85, alpha: a });
  });
}
function earthLayer(g, key, stops, dx, dy, alpha, R) {
  const E = DATA.earth, X = lo => R.x + R.w * (lo + 180) / 360 + dx, Y = la => R.y + R.h * (84 - la) / 144 + dy, r = Math.max(1.2, R.w / 260);
  g.rect(R.x + dx - 4, R.y + dy - 4, R.w + 8, R.h + 8, { fill: g.C.bg, stroke: g.C.line, r: 6, alpha: alpha });
  for (let i = 0; i < E.lon.length; i++) g.dot(X(E.lon[i]), Y(E.lat[i]), r, g.ramp(E[key][i] / 255, stops), alpha);
}
function sCube(g, t) {
  const { C } = g, w = g.W * (g.narrow ? .74 : .56), R = { x: g.X(g.narrow ? .18 : .3), y: g.Y(g.narrow ? .44 : .46), w, h: w * .4 }, off = g.W * .045;
  head(g, "The cube: every layer on the same cells");
  for (let k = 5; k >= 2; k--) g.rect(R.x - off * (1 + (k - 1) * .35) - 4, R.y - off * 1.5 * (1 + (k - 1) * .35) - 4, R.w + 8, R.h + 8, { stroke: C.line, r: 6, alpha: g.seg(t, .55 + (5 - k) * .06, .75 + (5 - k) * .06) });
  const a2 = g.seg(t, .3, .55);
  if (a2 > 0) earthLayer(g, "temp", TEMP, -off, -off * 1.5 - (1 - a2) * g.H * .2, a2, R);
  earthLayer(g, "rough", COOL, 0, 0, g.seg(t, 0, .25), R);
  g.text("roughness at 21 km", R.x, R.y + R.h + g.fs(1.6), { color: C.earth, weight: 600, alpha: g.seg(t, .1, .3) });
  g.text("temperature level", R.x - off, R.y - off * 1.5 - g.fs(1.3), { color: C.mars, weight: 600, alpha: a2 });
  g.text(fmt(DATA.num.ref_cells) + " land cells · 14 layers · real data", R.x + R.w, R.y + R.h + g.fs(1.6), { align: "right", color: C.mute, alpha: g.seg(t, .8, 1), size: .9 });
}

/* ---------------------------------------------------------------- 3 one scale */
const RX = (g, v) => g.X(.08 + .84 * (v - .1) / 3.1);
function swarm(g, vals, y, col, alpha, seed, spread) { vals.forEach((v, i) => g.dot(RX(g, v), y + (g.rnd(i + seed) - .5) * g.H * (spread || .12), 3, col, alpha * .8)); }
function axisRough(g, y, a) { g.line(RX(g, .1), y, RX(g, 3.2), y, { color: g.C.line, alpha: a }); [1, 10, 100, 1000].forEach(v => { g.line(RX(g, Math.log10(v)), y - 4, RX(g, Math.log10(v)), y + 4, { color: g.C.mute, alpha: a }); g.text(v + " m", RX(g, Math.log10(v)), y + g.fs(1.1), { align: "center", color: g.C.mute, size: .82, alpha: a }); }); }
function sPooled(g, t) {
  const { C } = g, D = DATA.mm, n = g.narrow, X = v => g.X(.08 + .84 * (v - D.lo) / (D.hi - D.lo)), yE = g.Y(.27), yM = g.Y(.45), yA = g.Y(.58), yR = g.Y(.74);
  head(g, "One straight scale for both worlds");
  D.earth.forEach((v, i) => g.dot(X(v), yE + (g.rnd(i + 5) - .5) * g.H * .12, 2.6, C.earth, .7 * g.seg(t, 0, .14)));
  D.moon.forEach((v, i) => g.dot(X(v), yM + (g.rnd(i + 700) - .5) * g.H * .12, 2.6, C.moon, .7 * g.seg(t, .07, .2)));
  g.text(n ? "Earth" : "Earth · roughness at 21 km", X(D.hi * .32), yE, { color: C.earth, weight: 600, alpha: g.seg(t, 0, .14) });
  g.text("Moon", X(D.hi * .72), yM, { color: C.moon, weight: 600, alpha: g.seg(t, .07, .2) });
  g.line(X(D.lo), yA, X(D.hi), yA, { color: C.line });
  [500, 1000, 1500, 2000].forEach(v => { g.line(X(v), yA - 4, X(v), yA + 4, { color: C.line }); g.text(fmt(v) + " m", X(v), yA + g.fs(1.1), { align: "center", color: C.mute, size: .82 }); });
  const e = g.seg(t, .24, .4);
  [[D.lo, "smallest on either world", "left"], [D.hi, "largest: " + fmt(Math.round(D.hi)) + " m, on the " + (D.hi_set_by === "moon" ? "Moon" : "Earth"), "right"]].forEach(([v, lab, al]) => {
    g.line(X(v), yE - g.H * .09, X(v), yR, { color: C.hi, w: 1.5, dash: [5, 4], alpha: e });
    if (!n) g.text(lab, X(v) + (al === "left" ? 6 : -6), yE - g.H * .11, { align: al, color: C.hi, size: .85, weight: 600, alpha: e });
  });
  const a = g.seg(t, .42, .56);
  g.line(X(D.lo), yR, X(D.hi), yR, { color: C.ink, w: 2, alpha: a });
  [0, .25, .5, .75, 1].forEach(q => { const x = X(D.lo + q * (D.hi - D.lo)); g.line(x, yR - 5, x, yR + 5, { color: C.ink, alpha: a }); g.text(String(q), x, yR - g.fs(1.2), { align: "center", color: C.mute, size: .82, alpha: a }); });
  g.text("position: how far along, from smallest (0) to largest (1)", X(D.hi), yR + g.fs(1.3), { align: "right", color: C.mute, alpha: a, size: n ? .78 : .9 });
  [[D.earth_median, C.earth, "Earth's middle cell", .6, 2.9], [D.moon_median, C.moon, "the Moon's middle cell", .76, 4.5]].forEach(([v, col, lab, st, row]) => {
    const b = g.seg(t, st, st + .16), q = (v - D.lo) / (D.hi - D.lo);
    if (b > 0) { g.line(X(v), yA, X(v), g.lerp(yA, yR, b), { color: col, w: 2 }); g.dot(X(v), g.lerp(yA, yR, b), 6, col); }
    g.text((n ? "" : lab + ", ") + Math.round(v) + " m  →  " + q.toFixed(2), X(v) + 10, yR + g.fs(row), { color: col, weight: 600, alpha: g.seg(t, st + .1, st + .2), size: .9 });
  });
}
function sNoOverlap(g, t) {
  const { C } = g, D = DATA.temp, X = v => g.X(.08 + .84 * (v - 130) / 185), y = g.Y(.46);
  head(g, "Where the worlds do not overlap, the scale says so");
  g.line(X(130), y + g.H * .13, X(315), y + g.H * .13, { color: C.line }); [150, 200, 250, 300].forEach(v => g.text(v + " K", X(v), y + g.H * .13 + g.fs(1.1), { align: "center", color: C.mute, size: .82 }));
  D.moon.forEach((v, i) => g.dot(X(v), y + (g.rnd(i + 5) - .5) * g.H * .2, 3, C.moon, .8 * g.seg(t, 0, .3)));
  D.earth.forEach((v, i) => g.dot(X(v), y + (g.rnd(i + 900) - .5) * g.H * .2, 3, C.earth, .8 * g.seg(t, .15, .45)));
  g.text("Moon · temperature level", X(150), y - g.H * .17, { color: C.moon, weight: 600 }); g.text("Earth", X(300), y - g.H * .17, { color: C.earth, weight: 600, align: "right" });
  const mx = Math.max(...D.moon), mn = Math.min(...D.earth), a = g.seg(t, .5, .75);
  g.rect(X(mx), y - g.H * .13, X(mn) - X(mx), g.H * .26, { fill: C.bad, alpha: .22 * a }); g.line(X(mx), y - g.H * .13, X(mx), y + g.H * .13, { color: C.bad, alpha: a }); g.line(X(mn), y - g.H * .13, X(mn), y + g.H * .13, { color: C.bad, alpha: a });
  g.text("no overlap", (X(mx) + X(mn)) / 2, y - g.H * .2, { align: "center", color: C.bad, weight: 600, alpha: a });
  g.text(g.narrow ? "Reported as Earth's limit, in kelvin." : "Reported as Earth's limit, with the gap in kelvin, on every result.", g.X(.5), g.Y(.88), { align: "center", alpha: g.seg(t, .78, 1), size: g.narrow ? .8 : 1 });
}
function sNormal(g, t) {
  const { C } = g, c = DATA.curve, n = g.narrow;
  const val = q => { for (let i = 1; i < c.p.length; i++) if (q <= c.p[i]) return Math.pow(10, c.x[i - 1] + (c.x[i] - c.x[i - 1]) * (q - c.p[i - 1]) / (c.p[i] - c.p[i - 1])); return Math.pow(10, c.x[c.x.length - 1]); };
  const P = [[.5, "a middling cell"], [.9, "a rough cell"], [.995, "one of the roughest"]], y1 = g.Y(.36), y2 = g.Y(.76), X1 = q => g.X(.1 + .8 * q), X2 = z => g.X(.5 + .14 * z);
  head(g, "From position to score");
  g.text("position on the shared scale", g.X(.1), y1 + g.fs(2.6), { color: C.mute, size: .88 });
  g.line(X1(0), y1, X1(1), y1, { color: C.ink, w: 2 }); [0, .25, .5, .75, 1].forEach(q => { g.line(X1(q), y1 - 5, X1(q), y1 + 5, { color: C.ink }); g.text(String(q), X1(q), y1 + g.fs(1.2), { align: "center", color: C.mute, size: .82 }); });
  const a2 = g.seg(t, .32, .46);
  g.line(X2(-3.2), y2, X2(3.2), y2, { color: C.ink, w: 2, alpha: a2 }); [-3, -2, -1, 0, 1, 2, 3].forEach(z => { g.line(X2(z), y2 - 5, X2(z), y2 + 5, { color: C.ink, alpha: a2 }); g.text(String(z), X2(z), y2 + g.fs(1.2), { align: "center", color: C.mute, size: .82, alpha: a2 }); });
  g.text("score", X2(-3.2), y2 + g.fs(2.6), { color: C.mute, size: .88, alpha: a2 });
  const bell = []; for (let k = -32; k <= 32; k++) bell.push([X2(k / 10), y2 - 6 - g.H * .15 * Math.exp(-k * k / 200)]);
  g.poly(bell, { stroke: C.mute, w: 1.2, alpha: a2 * .6 });
  P.forEach(([q, lab], i) => {
    const a = g.seg(t, .06 + i * .08, .2 + i * .08), m = g.seg(t, .48 + i * .1, .72 + i * .1), z = invNorm(q), col = i === 2 ? C.hi : i === 1 ? C.mars : C.earth;
    g.line(X1(q), y1 - 12, X1(q), y1 + 12, { color: col, w: 3, alpha: a });
    const ly = y1 - g.fs(1.7) - (i === 2 ? g.fs(1.5) : 0), al = i === 0 ? "center" : "right", lx = i === 0 ? X1(q) : i === 1 ? X1(q) - 6 : X1(1);
    g.text((n ? "" : lab + ": ") + fmt(val(q)) + " m", lx, ly, { align: al, color: col, weight: 600, alpha: a, size: .9 });
    if (m > 0) { g.line(X1(q), y1 + 12, g.lerp(X1(q), X2(z), m), g.lerp(y1 + 12, y2 - 10, m), { color: col, w: 1.5, dash: [4, 4], alpha: .8 }); g.dot(g.lerp(X1(q), X2(z), m), g.lerp(y1 + 12, y2 - 10, m), 6, col); }
    g.text(z.toFixed(1), X2(z), y2 - g.fs(2.5), { align: "center", color: col, weight: 700, alpha: g.seg(t, .7 + i * .1, .8 + i * .1) });
  });
  g.text("0.90 and 0.995 sit close together here", X1(.95), y1 + g.fs(4.2), { align: "right", color: C.mute, alpha: g.seg(t, .25, .4) * (1 - g.seg(t, .9, 1)), size: .88 });
  g.text("the roughest cell now stands clearly apart", g.X(.5), g.Y(.94), { align: "center", color: C.hi, weight: 600, alpha: g.seg(t, .9, 1) });
}

/* ---------------------------------------------------------------- 4 whitening */
function whitenFrame(g, s, R) {
  const side = Math.min(g.W * (g.narrow ? .86 : .5), g.H * (g.narrow ? .6 : .76)), cx = g.narrow ? g.X(.5) : g.X(.34), cy = g.narrow ? g.Y(.44) : g.Y(.54);
  const rho = DATA.whiten.corr, l1 = 1 / Math.sqrt(1 + rho), l2 = 1 / Math.sqrt(1 - rho), a = g.lerp(1, (l1 + l2) / 2, s), b = g.lerp(0, (l1 - l2) / 2, s);
  const P = (x, y) => [cx + (a * x + b * y) / R * side / 2, cy - (b * x + a * y) / R * side / 2];
  return { P, side, cx, cy, a, b };
}
function sWhitenA(g, t, s) {
  s = s || 0; const { C } = g, R = g.lerp(3.3, 6.4, s), F = whitenFrame(g, s, R), W = DATA.whiten;
  g.rect(F.cx - F.side / 2, F.cy - F.side / 2, F.side, F.side, { stroke: C.line, r: 6 });
  g.text(s > .5 ? "after the correction" : "roughness →", F.cx, F.cy + F.side / 2 + g.fs(1.1), { align: "center", color: C.mute, size: .85 });
  if (s < .5) { g.ctx.save(); g.ctx.translate(F.cx - F.side / 2 - g.fs(1), F.cy); g.ctx.rotate(-Math.PI / 2); g.text("slope →", 0, 0, { align: "center", color: C.mute, size: .85 }); g.ctx.restore(); }
  const a0 = s ? 1 : g.seg(t, 0, .3);
  W.x.forEach((x, i) => { const p = F.P(W.y[i], x); if (Math.abs(p[0] - F.cx) < F.side / 2 && Math.abs(p[1] - F.cy) < F.side / 2) g.dot(p[0], p[1], 2.6, C.earth, .55 * a0); });
  const T = F.P(0, 0), A = F.P(1.15, 1.15), B = F.P(1.15, -1.15), a1 = s ? 1 : g.seg(t, .3, .5), a2 = s ? 1 : g.seg(t, .5, .75);
  const dA = Math.hypot(A[0] - T[0], A[1] - T[1]) / (F.side / 2) * R, dB = Math.hypot(B[0] - T[0], B[1] - T[1]) / (F.side / 2) * R;
  if (!s) g.ring(T[0], T[1], Math.hypot(A[0] - T[0], A[1] - T[1]), C.mute, 1.5, a2 * .8);
  g.line(T[0], T[1], A[0], A[1], { color: C.good, w: 2.5, alpha: a2 }); g.line(T[0], T[1], B[0], B[1], { color: C.bad, w: 2.5, alpha: a2 });
  g.dot(T[0], T[1], 7, C.hi, a1); g.text("target", T[0] - 10, T[1] - g.fs(1), { align: "right", color: C.hi, weight: 600, alpha: a1 });
  g.dot(A[0], A[1], 6, C.good, a1); g.text("A", A[0] + 9, A[1] - 8, { color: C.good, weight: 700, alpha: a1 });
  g.dot(B[0], B[1], 6, C.bad, a1); g.text("B", B[0] + 9, B[1] + 8, { color: C.bad, weight: 700, alpha: a1 });
  const lx = g.narrow ? g.X(.08) : g.X(.66), ly = g.narrow ? g.Y(.82) : g.Y(.32), a3 = s ? g.seg(t, .7, 1) : g.seg(t, .75, 1);
  g.text("A: steeper and rougher", lx, ly, { color: C.good, weight: 600, alpha: a1 }); g.text("the usual pattern on Earth", lx, ly + g.fs(1.35), { color: C.mute, alpha: a1, size: .9 });
  g.text("B: steeper but smoother", lx, ly + g.fs(3.2), { color: C.bad, weight: 600, alpha: a1 }); g.text("against the pattern", lx, ly + g.fs(4.55), { color: C.mute, alpha: a1, size: .9 });
  g.text("distance to target   A " + dA.toFixed(1) + "   B " + dB.toFixed(1), lx, ly + g.fs(6.8), { weight: 600, alpha: a3 });
  g.text(s ? "B is the real surprise, and now it counts as one" : "by plain ruler they look equally far", lx, ly + g.fs(8.2), { color: s ? C.hi : C.mute, alpha: a3, size: .92 });
}
function sWhitenB(g, t) { head(g, "Measure in units of surprise"); sWhitenA(g, t, g.seg(t, .05, .65)); }
function sGroups(g, t) {
  const { C } = g, bx = boxes(g, 3, { top: .17, bot: .62 }), sh = DATA.num.share;
  head(g, "Three groups, each corrected on its own");
  [["Terrain", "8 variables", "worth about 4", C.earth], ["Thermal", "2 variables", "worth 2", C.mars], ["Composition", "2 variables", "worth 2", C.moon]].forEach((it, i) => {
    const a = g.seg(t, i * .13, i * .13 + .25), b = bx[i], m = g.seg(t, .4 + i * .08, .65 + i * .08);
    g.rect(b.x, b.y, b.w, b.h, { stroke: it[3], r: 10, alpha: a, w: 2 });
    const cx = b.x + b.w * (g.narrow ? .2 : .5), cy = b.y + b.h * (g.narrow ? .5 : .36), r = Math.min(b.w, b.h) * .22;
    g.ctx.save(); g.ctx.translate(cx, cy); g.ctx.rotate(-.6 * (1 - m)); g.ctx.scale(1, g.lerp(.3, 1, m)); g.ctx.beginPath(); g.ctx.arc(0, 0, r, 0, 6.2832); g.ctx.restore();
    g.ctx.save(); g.ctx.globalAlpha = a * .35; g.ctx.fillStyle = it[3]; g.ctx.fill(); g.ctx.restore();
    const tx = g.narrow ? b.x + b.w * .42 : b.x + b.w / 2, ty = g.narrow ? b.y + b.h * .3 : b.y + b.h * .72, al = g.narrow ? "left" : "center";
    g.text(it[0], tx, ty, { align: al, weight: 600, color: it[3], alpha: a }); g.text(it[1] + ", " + it[2], tx, ty + g.fs(1.4), { align: al, color: C.mute, alpha: a, size: .88 });
  });
  const a = g.seg(t, .7, .95), x0 = g.X(.06), w = g.W * .88, y = g.Y(.76), parts = [[sh.terrain, C.earth, "terrain"], [sh.thermal, C.mars, "thermal"], [sh.composition, C.moon, "composition"]];
  let x = x0; const tot = sh.terrain + sh.thermal + sh.composition;
  g.text("share of a typical difference between two Earth cells", x0, y - g.fs(1.3), { color: C.mute, alpha: a, size: .9 });
  parts.forEach(p => { const ww = w * p[0] / tot * a; g.rect(x + 1, y, Math.max(0, ww - 2), g.fs(1.8), { fill: p[1], r: 4, alpha: a }); g.text(p[2] + " " + p[0] + "%", x + ww / 2, y + g.fs(3), { align: "center", color: p[1], weight: 600, alpha: a, size: .88 }); x += w * p[0] / tot; });
}

/* ---------------------------------------------------------------- 5 target */
function poleMap(g, alpha, hiName, t, box) {
  const { C } = g, P = DATA.pole;
  const side = box ? box.side : Math.min(g.H * (g.narrow ? .56 : .8), g.W * (g.narrow ? .9 : .5)), cx = box ? box.cx : (g.narrow ? g.X(.5) : g.X(.32)), cy = box ? box.cy : (g.narrow ? g.Y(.4) : g.Y(.55)), sc = side / 440, cs = 6.95 * sc;
  const X = x => cx + x * sc, Y = y => cy - y * sc;
  for (let i = 0; i < P.x.length; i++) {
    const d = Math.hypot(P.x[i], P.y[i]) / 215, a = alpha == null ? g.seg(t, d * .35, d * .35 + .15) : alpha;
    if (a > 0 && P.t[i] >= 0) g.rect(X(P.x[i]) - cs * .7, Y(P.y[i]) - cs * .7, cs * 1.4, cs * 1.4, { fill: g.ramp((P.t[i] - P.tmin) / (P.tmax - P.tmin), TEMP), alpha: a });
  }
  DATA.regions.forEach((r, k) => {
    if (box && r.name !== hiName) return;
    const a = alpha == null ? g.seg(t, .45 + k * .04, .6 + k * .04) : 1, hot = r.name === hiName, pts = r.vx.map((x, j) => [X(x), Y(r.vy[j])]);
    g.poly(pts, { stroke: hot ? C.hi : C.ink, w: hot ? 3 : 1.5, close: true, alpha: a * (hiName && !hot ? .45 : 1) });
    if (hot) r.idx.forEach((j, q) => g.rect(X(P.x[j]) - cs / 2, Y(P.y[j]) - cs / 2, cs, cs, { stroke: C.hi, w: 1.5, alpha: box ? 1 : g.seg(t, .15 + q * .03, .3 + q * .03) }));
  });
  return { X, Y, side, cx, cy, sc, cs };
}
function sPole(g, t) {
  const { C } = g, M = poleMap(g, null, null, t), lx = g.narrow ? g.X(.06) : g.X(.63), ly = g.narrow ? g.Y(.76) : g.Y(.26), a = g.seg(t, .2, .45);
  head(g, "The Moon's south pole, cell by cell");
  g.text("temperature level", lx, ly, { weight: 600, alpha: a });
  const w = g.W * (g.narrow ? .5 : .26); for (let k = 0; k < 40; k++) g.rect(lx + w * k / 40, ly + g.fs(1), w / 40 + 1, g.fs(1), { fill: g.ramp(k / 39, TEMP), alpha: a });
  g.text("40 K", lx, ly + g.fs(2.9), { color: C.mute, size: .85, alpha: a }); g.text("240 K", lx + w, ly + g.fs(2.9), { color: C.mute, size: .85, align: "right", alpha: a });
  if (!g.narrow) {
    g.text(fmt(DATA.pole.x.length) + " cells, each 6.9 km across", lx, ly + g.fs(5.4), { color: C.mute, alpha: a });
    g.text("Outlined: the nine regions NASA", lx, ly + g.fs(8), { alpha: g.seg(t, .6, .8) }); g.text("is considering for Artemis III", lx, ly + g.fs(9.4), { alpha: g.seg(t, .6, .8) });
    g.text("real data", lx, ly + g.fs(12), { color: C.hi, weight: 600, alpha: g.seg(t, .8, 1) });
  } else g.text("outlined: nine Artemis III regions · real data", lx, ly + g.fs(4.6), { color: C.hi, size: .88, alpha: g.seg(t, .6, .8) });
}
function sSelect(g, t) {
  const { C } = g; poleMap(g, .55, "Haworth", t);
  head(g, "A target is a set of cells");
  const lx = g.narrow ? g.X(.06) : g.X(.63), ly = g.narrow ? g.Y(.74) : g.Y(.26), n = Math.round(DATA.num.haworth_cells * g.seg(t, .15, .6));
  g.text("Haworth", lx, ly, { color: C.hi, weight: 700, size: 1.3, display: true });
  g.text(n + " cells", lx, ly + g.fs(2.2), { weight: 600, size: 1.15 });
  const a = g.seg(t, .6, .85);
  g.text("each cell carries 12 numbers", lx, ly + g.fs(4.4), { color: C.mute, alpha: a });
  for (let k = 0; k < 12; k++) g.rect(lx + k * g.fs(1.25), ly + g.fs(7.4) - g.fs(2) * (.25 + .75 * g.rnd(k + 3)) * a, g.fs(.9), g.fs(2) * (.25 + .75 * g.rnd(k + 3)) * a, { fill: k < 8 ? C.earth : k < 10 ? C.mars : C.moon, r: 2, alpha: a });
  if (!g.narrow) { g.text("On Mars a target is a 100 km zone:", lx, ly + g.fs(10.4), { color: C.mute, alpha: g.seg(t, .85, 1) }); g.text("about 680 cells.", lx, ly + g.fs(11.8), { color: C.mute, alpha: g.seg(t, .85, 1) }); }
}

/* ---------------------------------------------------------------- 6 distance */
function spaceFrame(g) {
  const S = DATA.space, x0 = g.X(g.narrow ? .12 : .1), x1 = g.X(g.narrow ? .94 : .66), y0 = g.Y(.14), y1 = g.Y(g.narrow ? .7 : .88);
  if (!S.ext) { const xs = S.ex.concat(S.tx), ys = S.ey.concat(S.ty), pad = (a, b) => [a - .06 * (b - a), b + .06 * (b - a)]; S.ext = { x: pad(Math.min(...xs), Math.max(...xs)), y: pad(Math.min(...ys), Math.max(...ys)) }; }
  const E = S.ext;
  return { X: v => x0 + (x1 - x0) * (v - E.x[0]) / (E.x[1] - E.x[0]), Y: v => y1 - (y1 - y0) * (v - E.y[0]) / (E.y[1] - E.y[0]), x0, x1, y0, y1 };
}
function spaceScores() {
  const S = DATA.space; if (S.score) return S;
  S.score = S.ex.map((x, i) => S.tx.reduce((a, tx, j) => a + Math.hypot(x - tx, S.ey[i] - S.ty[j]), 0) / S.tx.length);
  S.order = S.score.map((s, i) => i).sort((a, b) => S.score[a] - S.score[b]);
  S.pick = S.order[Math.floor(S.order.length * .45)];
  S.near = S.tx.map((tx, j) => [Math.hypot(S.ex[S.pick] - tx, S.ey[S.pick] - S.ty[j]), j]).sort((a, b) => a[0] - b[0]).map(q => q[1]);
  S.max = Math.max(...S.score); S.min = Math.min(...S.score); return S;
}
function sSpace(g, t, mode) {
  const { C } = g, S = spaceScores(), F = spaceFrame(g);
  g.line(F.x0, F.y1, F.x1, F.y1, { color: C.line }); g.line(F.x0, F.y0, F.x0, F.y1, { color: C.line });
  g.text("rougher →", F.x1, F.y1 + g.fs(1.1), { align: "right", color: C.mute, size: .85 }); g.text("↑ ridge · bowl ↓", F.x0 + 6, F.y0 + 4, { color: C.mute, size: .85 });
  const aE = mode ? 1 : g.seg(t, 0, .35), aT = mode ? 1 : g.seg(t, .4, .6), c = mode === 2 ? g.seg(t, 0, .6) : 0;
  S.ex.forEach((x, i) => {
    const cl = 1 - (S.score[i] - S.min) / (S.max - S.min), top = S.order.indexOf(i) < 6;
    g.dot(F.X(x), F.Y(S.ey[i]), g.lerp(3, 2 + 5 * cl * cl, c), c > 0 ? g.ramp(cl, COOL) : C.earth, aE * g.lerp(.6, .25 + .75 * cl, c));
    if (mode === 2 && top) g.ring(F.X(x), F.Y(S.ey[i]), 10, C.hi, 2, g.seg(t, .6, .85));
  });
  S.tx.forEach((x, j) => g.rect(F.X(x) - 4.5, F.Y(S.ty[j]) - 4.5, 9, 9, { fill: C.hi, alpha: aT, r: 2 }));
  const lx = g.narrow ? g.X(.06) : g.X(.7), ly = g.narrow ? g.Y(.79) : g.Y(.26);
  g.dot(lx + 5, ly, 4, C.earth, aE); g.text("Earth cells", lx + 16, ly, { alpha: aE });
  g.rect(lx, ly + g.fs(1.5) - 5, 10, 10, { fill: C.hi, alpha: aT, r: 2 }); g.text("the 15 target cells", lx + 16, ly + g.fs(1.5), { alpha: aT });
  if (!mode) { g.text("rougher than almost all of Earth,", lx, ly + g.fs(4), { color: C.hi, weight: 600, alpha: g.seg(t, .7, .9) }); g.text("and far apart from each other", lx, ly + g.fs(5.4), { color: C.hi, weight: 600, alpha: g.seg(t, .7, .9) }); }
  if (mode === 1) {
    const px = F.X(S.ex[S.pick]), py = F.Y(S.ey[S.pick]);
    S.near.forEach((j, k) => { const a = g.seg(t, .12 + k * .04, .22 + k * .04); if (a > 0) g.line(px, py, g.lerp(px, F.X(S.tx[j]), a), g.lerp(py, F.Y(S.ty[j]), a), { color: C.hi, w: 1.8 }); });
    g.ring(px, py, 9, C.ink, 2); g.dot(px, py, 5, C.ink);
    g.text("take one Earth cell", lx, ly + g.fs(4), { weight: 600, alpha: g.seg(t, 0, .2) });
    g.text("measure to every target cell", lx, ly + g.fs(5.4), { color: C.mute, alpha: g.seg(t, .3, .5), size: .92 });
    g.text("score = average of the " + S.tx.length + " lines", lx, ly + g.fs(7.2), { color: C.hi, weight: 600, alpha: g.seg(t, .8, 1) });
  }
  if (mode === 2) { g.text("every Earth cell gets a score", lx, ly + g.fs(4), { weight: 600, alpha: g.seg(t, .2, .5) }); g.text("bright = close to the target", lx, ly + g.fs(5.4), { color: C.mute, alpha: g.seg(t, .4, .6), size: .92 }); g.text("ringed = the closest few", lx, ly + g.fs(6.8), { color: C.hi, alpha: g.seg(t, .7, .9), size: .92 }); }
}

/* ---------------------------------------------------------------- 7 null */
function nullData() {
  if (DATA.nul) return DATA.nul; const v = [], r = i => { const x = Math.sin(i * 91.7 + 3.3) * 43758.5453; return x - Math.floor(x); };
  for (let i = 0; i < 1000; i++) v.push(.12 + .3 * (r(i) + r(i + 1e4) + r(i + 2e4) + r(i + 3e4)) / 2.2);
  const bins = new Array(30).fill(0); v.forEach(x => bins[Math.min(29, Math.floor((x - .1) / .5 * 30))]++);
  const obs = .37; DATA.nul = { v, bins, obs, p: (1 + v.filter(x => x <= obs).length) / 1001, max: Math.max(...bins) }; return DATA.nul;
}
function nullPatches() {
  if (DATA.nulp) return DATA.nulp; const P = DATA.pole, N = nullData(), r = i => { const x = Math.sin(i * 53.1 + 7.7) * 43758.5453; return x - Math.floor(x); }, out = [], rin = 37, rout = 159;
  for (let k = 0; k < 34; k++) {
    const rad = Math.sqrt(rin * rin + (rout * rout - rin * rin) * r(k)), ang = r(k + 100) * 6.2832, cx = rad * Math.cos(ang), cy = rad * Math.sin(ang);
    const idx = P.x.map((x, i) => [Math.hypot(x - cx, P.y[i] - cy), i]).sort((a, b) => a[0] - b[0]).slice(0, 15).map(q => q[1]);
    out.push({ idx, score: N.v[k] });
  }
  DATA.nulp = { patches: out, rin, rout }; return DATA.nulp;
}
function nullBox(g) { return g.narrow ? { cx: g.X(.5), cy: g.Y(.33), side: Math.min(g.W * .8, g.H * .44) } : { cx: g.X(.27), cy: g.Y(.56), side: Math.min(g.H * .76, g.W * .46) }; }
function patchCells(g, M, idx, color, alpha) { const P = DATA.pole; idx.forEach(j => g.rect(M.X(P.x[j]) - M.cs / 2, M.Y(P.y[j]) - M.cs / 2, M.cs, M.cs, { fill: color, alpha: alpha * .55 })); idx.forEach(j => g.rect(M.X(P.x[j]) - M.cs / 2, M.Y(P.y[j]) - M.cs / 2, M.cs, M.cs, { stroke: color, w: 1, alpha })); }
function sAnySearch(g, t) {
  const { C } = g, Q = nullPatches(), N = nullData(), M = poleMap(g, .5, "Haworth", 1, nullBox(g));
  head(g, "Every search returns a winner");
  const rows = [["Haworth, the real target", C.hi, N.obs, null], ["a random patch of the Moon", C.ink, Q.patches[3].score, 3], ["another random patch", C.ink, Q.patches[11].score, 11]];
  const lx = g.narrow ? g.X(.08) : g.X(.56), ly = g.narrow ? g.Y(.62) : g.Y(.28);
  rows.forEach((r, i) => {
    const a = g.seg(t, i * .26, i * .26 + .16), b = g.seg(t, i * .26 + .12, i * .26 + .26), y = ly + i * g.fs(g.narrow ? 3.3 : 4.3);
    if (r[3] != null) patchCells(g, M, Q.patches[r[3]].idx, C.ink, a);
    g.rect(lx, y - 7, 14, 14, { fill: i ? null : C.hi, stroke: r[1], r: 2, alpha: a }); g.text(r[0], lx + 24, y, { weight: 600, alpha: a, size: g.narrow ? .9 : 1 });
    g.text("its best match on Earth scores " + r[2].toFixed(2), lx + 24, y + g.fs(1.4), { color: C.mute, alpha: b, size: .9 });
  });
  g.text("A best match, alone, proves nothing.", g.narrow ? g.X(.5) : lx, g.narrow ? g.Y(.95) : ly + g.fs(14), { align: g.narrow ? "center" : "left", color: C.hi, weight: 600, size: 1.05, alpha: g.seg(t, .85, 1) });
}
function sNull(g, t) {
  const { C } = g, Q = nullPatches(), N = nullData(), M = poleMap(g, .45, "Haworth", 1, nullBox(g)), n = g.narrow;
  head(g, "Compare with 1,000 random patches");
  [Q.rin, Q.rout].forEach(rr => { g.ctx.save(); g.ctx.setLineDash([5, 5]); g.ring(M.cx, M.cy, rr * M.sc, C.ink, 1.2, .7 * g.seg(t, 0, .1)); g.ctx.restore(); });
  Q.patches.forEach((q, k) => { const a = g.seg(t, .06 + k * .012, .09 + k * .012); if (a > 0) patchCells(g, M, q.idx, C.ink, a * g.lerp(1, .45, g.seg(t, .12 + k * .012, .2 + k * .012))); });
  g.text("between the dashed rings: the same latitude as the target", M.cx, M.cy + M.side / 2 + g.fs(1), { align: "center", color: C.mute, size: .82, alpha: g.seg(t, .05, .2) });
  const x0 = n ? g.X(.1) : g.X(.56), x1 = n ? g.X(.9) : g.X(.95), y1 = n ? g.Y(.86) : g.Y(.76), h = g.H * (n ? .2 : .42), cnt = Math.round(1000 * g.seg(t, .1, .62)), X = v => x0 + (x1 - x0) * (v - .1) / .5;
  const bins = new Array(30).fill(0); for (let i = 0; i < cnt; i++) bins[Math.min(29, Math.floor((N.v[i] - .1) / .5 * 30))]++;
  const sh = g.seg(t, .78, .94);
  bins.forEach((b, k) => { const left = .1 + (k + 1) * .5 / 30 <= N.obs + .001; g.rect(x0 + (x1 - x0) * k / 30 + 1, y1 - h * b / N.max, (x1 - x0) / 30 - 2, h * b / N.max, { fill: left && sh > 0 ? C.hi : C.mute, alpha: left ? g.lerp(.55, .95, sh) : .55, r: 2 }); });
  g.line(x0, y1, x1, y1, { color: C.line }); g.text("best-match score of each random patch", (x0 + x1) / 2, y1 + g.fs(1.2), { align: "center", color: C.mute, size: .82 });
  g.text(fmt(cnt) + " random patches searched", x0, y1 - h - g.fs(n ? 1.2 : 2.6), { color: C.mute, size: .9 });
  const a = g.seg(t, .62, .76); g.line(X(N.obs), y1, X(N.obs), y1 - h * 1.05 * a, { color: C.hi, w: 3 }); g.text("Haworth", X(N.obs) + 6, y1 - h * 1.04, { color: C.hi, weight: 600, alpha: a, size: .92 });
  g.text(Math.round(N.p * 100) + " in 100 random patches did as well:  p = " + N.p.toFixed(2), n ? g.X(.5) : (x0 + x1) / 2, n ? g.Y(.96) : y1 + g.fs(3.4), { align: "center", weight: 600, alpha: g.seg(t, .9, 1), size: n ? .85 : 1 });
}

function sControl(g, t) {
  const { C } = g, n = g.narrow, bx = boxes(g, 2, { top: .5, bot: .92 }), cx = g.X(.5);
  head(g, "First, test the test");
  const a0 = g.seg(t, 0, .2), side = Math.min(g.W * .09, g.H * .12), px = n ? g.X(.08) : g.X(.12), py = g.Y(.2);
  for (let j = 0; j < 4; j++) for (let i = 0; i < 5; i++) g.rect(px + i * side / 5, py + j * side / 4, side / 5 + .5, side / 4 + .5, { fill: g.ramp(.35 + .5 * g.rnd(i * 7 + j), COOL), alpha: a0 });
  g.rect(px, py, side, side * 1.0, { stroke: C.earth, w: 2, alpha: a0 });
  g.text("20 cells of the Atacama desert", px + side + 14, py + side * .3, { weight: 600, alpha: a0, size: n ? .9 : 1 });
  g.text("Earth ground: a perfect match exists on Earth", px + side + 14, py + side * .3 + g.fs(1.5), { color: C.mute, alpha: a0, size: n ? .78 : .9 });
  g.text("Run it through the same chance test as any target.", n ? g.X(.08) : px, g.Y(.42), { color: C.ink, alpha: g.seg(t, .2, .4), size: n ? .82 : .95 });
  [["The test finds it", "p below 0.05", "The test can see a match when one exists. A real target that comes back 'not significant' then means something.", C.good],
   ["The test misses it", "p above 0.05", "The test is blind. No p-value from it means anything, and we say so next to every result.", C.bad]].forEach((r, i) => {
    const b = bx[i], al = g.seg(t, .4 + i * .25, .58 + i * .25);
    g.rect(b.x, b.y, b.w, b.h, { fill: C.panel, stroke: r[3], r: 10, alpha: al, w: 2 });
    g.text(r[0], b.x + b.w * .07, b.y + b.h * .2, { weight: 700, color: r[3], alpha: al, size: 1.05 });
    g.text(r[1], b.x + b.w * .93, b.y + b.h * .2, { align: "right", color: C.mute, alpha: al, size: .88 });
    wrapText(g, r[2], b.x + b.w * .07, b.y + b.h * .42, b.w * .86, { color: C.ink, alpha: al, size: n ? .78 : .9 });
  });
}
function wrapText(g, s, x, y, w, o) {
  const words = s.split(" "), cw = g.fs(o.size || 1) * .52; let ln = "", k = 0;
  words.forEach(wd => { if ((ln + " " + wd).length * cw > w && ln) { g.text(ln, x, y + k * g.fs(1.45 * (o.size || 1)), o); k++; ln = wd; } else ln = ln ? ln + " " + wd : wd; });
  if (ln) g.text(ln, x, y + k * g.fs(1.45 * (o.size || 1)), o);
}

/* ---------------------------------------------------------------- 8 sites */
function field() {
  if (DATA.fld) return DATA.fld; const nx = 48, ny = 26, f = [], B = [[.24, .34, .1, 1], [.64, .62, .1, .58], [.82, .26, .08, .54], [.42, .8, .07, .5], [.08, .72, .06, .44]];
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const u = (i + .5) / nx, v = (j + .5) / ny; let q = .12 * Math.sin(u * 9) * Math.cos(v * 7) + .1; B.forEach(b => q += b[3] * Math.exp(-((u - b[0]) ** 2 + (v - b[1]) ** 2) / (2 * b[2] * b[2]))); f.push(q); }
  const mean = f.reduce((a, b) => a + b, 0) / f.length, varr = f.reduce((a, b) => a + (b - mean) ** 2, 0) / f.length, acf = [];
  for (let l = 0; l <= 16; l++) { let sum = 0, cnt = 0; for (let j = 0; j < ny; j++) for (let i = 0; i + l < nx; i++) { sum += (f[j * nx + i] - mean) * (f[j * nx + i + l] - mean); cnt++; } acf.push(sum / cnt / varr); }
  let reach = 16; for (let l = 1; l <= 16; l++) if (acf[l] < .37) { reach = l - 1 + (acf[l - 1] - .37) / (acf[l - 1] - acf[l]); break; }
  const order = f.map((q, i) => i).sort((a, b) => f[b] - f[a]), picks = [], R = reach / nx;
  for (const i of order) { const u = (i % nx + .5) / nx, v = (Math.floor(i / nx) + .5) / ny; if (picks.every(q => Math.hypot((q.u - u), (q.v - v) * ny / nx) > R)) picks.push({ u, v }); if (picks.length === 6) break; }
  DATA.fld = { nx, ny, f, order, picks, R, reach, acf, max: Math.max(...f) }; return DATA.fld;
}
function drawField(g, x0, y0, w) { const F = field(), hgt = w * F.ny / F.nx, cw = w / F.nx, ch = hgt / F.ny; F.f.forEach((q, i) => g.rect(x0 + (i % F.nx) * cw, y0 + Math.floor(i / F.nx) * ch, cw + .6, ch + .6, { fill: g.ramp(q / F.max, COOL), alpha: .9 })); return { hgt, cw, ch }; }
function sSites(g, t, mode) {
  const { C } = g, F = field(), n = g.narrow;
  head(g, mode === 2 ? "Take the best, clear the area around it, repeat" : mode === 1 ? "How far does similar ground reach?" : "The best cells are all in one valley");
  if (mode === 1) {
    const w = n ? g.W * .88 : g.W * .5, x0 = g.X(.06), y0 = g.Y(.16), D = drawField(g, x0, y0, w), q = F.picks[0], px = x0 + q.u * w, py = y0 + q.v * D.hgt;
    g.ctx.save(); g.ctx.beginPath(); g.ctx.rect(x0, y0, w, D.hgt); g.ctx.clip();
    [[2, "almost the same"], [F.reach, "starting to differ"], [14, "unrelated"]].forEach((r, k) => { const a = g.seg(t, .08 + k * .12, .22 + k * .12); g.ring(px, py, r[0] * D.cw, k === 1 ? C.hi : C.ink, k === 1 ? 2.5 : 1.5, a); const rr = r[0] * D.cw, lp = k === 0 ? [px + rr + 7, py - g.fs(.9), "left"] : k === 1 ? [px + rr * .74 + 5, py + rr * .74 + 6, "left"] : [px + rr * .5 - 8, py + rr * .87 - g.fs(.9), "right"];
      g.text(r[1], lp[0], lp[1], { color: k === 1 ? C.hi : C.ink, size: .82, weight: 600, alpha: a, align: lp[2] }); });
    g.ctx.restore(); g.dot(px, py, 5, C.hi);
    const cx0 = n ? g.X(.14) : g.X(.64), cx1 = n ? g.X(.9) : g.X(.94), cy1 = n ? g.Y(.9) : g.Y(.7), ch = g.H * (n ? .2 : .42), X = l => cx0 + (cx1 - cx0) * l / 16, Y = v => cy1 - ch * Math.max(0, v);
    g.line(cx0, cy1, cx1, cy1, { color: C.line }); g.line(cx0, cy1, cx0, cy1 - ch, { color: C.line });
    g.text("distance between two cells →", cx1, cy1 + g.fs(1.1), { align: "right", color: C.mute, size: .82 }); g.text("how alike their scores are", cx0, cy1 - ch - g.fs(1), { color: C.mute, size: .82 });
    const m = Math.round(16 * g.seg(t, .35, .7)), pts = []; for (let l = 0; l <= m; l++) pts.push([X(l), Y(F.acf[l])]);
    if (pts.length > 1) g.poly(pts, { stroke: C.earth, w: 2.5 });
    const a = g.seg(t, .72, .9); g.line(X(F.reach), cy1, X(F.reach), Y(.37), { color: C.hi, w: 2.5, dash: [5, 4], alpha: a }); g.dot(X(F.reach), Y(.37), 5, C.hi, a);
    g.text("the clearing distance", X(F.reach) + 8, Y(.37) - g.fs(.4), { color: C.hi, weight: 600, alpha: a, size: .92 });
    return;
  }
  const x0 = g.X(.06), w = g.W * .88, y0 = g.Y(.16), D = drawField(g, x0, y0, Math.min(w, g.H * .62 * F.nx / F.ny)), hgt = D.hgt, ww = D.cw * F.nx;
  if (!mode) { F.order.slice(0, 20).forEach((i, k) => { const a = g.seg(t, .15 + k * .03, .3 + k * .03); g.ring(x0 + (i % F.nx + .5) * D.cw, y0 + (Math.floor(i / F.nx) + .5) * D.ch, D.cw * .55, C.hi, 2, a); }); g.text("twenty pins on the same spot tell you one thing, twenty times", x0 + ww / 2, y0 + hgt + g.fs(2), { align: "center", color: C.mute, alpha: g.seg(t, .8, 1), size: n ? .8 : .95 }); return; }
  g.ctx.save(); g.ctx.beginPath(); g.ctx.rect(x0, y0, ww, hgt); g.ctx.clip();
  F.picks.forEach((q, k) => { const a = g.seg(t, k * .15, k * .15 + .1), r = g.seg(t, k * .15 + .05, k * .15 + .2), px = x0 + q.u * ww, py = y0 + q.v * hgt; g.dot(px, py, F.R * ww * r, C.bg, .5 * a); g.ring(px, py, F.R * ww * r, C.hi, 1.5, a * .8); });
  g.ctx.restore();
  F.picks.forEach((q, k) => { const a = g.seg(t, k * .15, k * .15 + .1), px = x0 + q.u * ww, py = y0 + q.v * hgt; g.dot(px, py, g.fs(.95), C.hi, a); g.text(String(k + 1), px, py + 1, { align: "center", color: C.bg, weight: 700, alpha: a, size: .95 }); });
  g.text("each circle is one clearing distance wide", x0 + ww / 2, y0 + hgt + g.fs(2), { align: "center", color: C.mute, alpha: g.seg(t, .85, 1), size: n ? .82 : .95 });
}

function fieldRank() { const F = field(); if (F.rank) return F; F.rank = new Array(F.f.length); F.order.forEach((i, k) => { F.rank[i] = k / F.f.length; }); return F; }
function fieldPatches(share) {
  const F = fieldRank(), key = "p" + share; if (F[key]) return F[key];
  const N = F.f.length, inb = F.rank.map(r => r < share), lab = new Array(N).fill(-1), out = [];
  for (const s0 of F.order) {
    if (!inb[s0]) break; if (lab[s0] >= 0) continue; const id = out.length, st = [s0], cells = []; lab[s0] = id;
    while (st.length) { const c = st.pop(), ci = c % F.nx, cj = Math.floor(c / F.nx); cells.push(c);
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) { const i = ci + di, j = cj + dj; if (i < 0 || j < 0 || i >= F.nx || j >= F.ny) continue; const q = j * F.nx + i; if (inb[q] && lab[q] < 0) { lab[q] = id; st.push(q); } } }
    out.push({ best: s0, cells });
  }
  F[key] = out; return out;
}
function sSlider(g, t) {
  const { C } = g, F = fieldRank(), TOP = .2;
  head(g, "Slide to widen the band");
  const x0 = g.X(.06), w = Math.min(g.W * .88, g.H * .54 * F.nx / F.ny), y0 = g.Y(.16), cw = w / F.nx, hgt = w * F.ny / F.nx, ch = hgt / F.ny;
  const u = g.seg(t, .08, .92), share = u < .15 ? .01 : u < .45 ? g.lerp(.01, .05, (u - .15) / .3) : u < .58 ? .05 : g.lerp(.05, TOP, Math.min(1, (u - .58) / .34));
  F.f.forEach((q, i) => { const r = F.rank[i], on = r < share; g.rect(x0 + (i % F.nx) * cw, y0 + Math.floor(i / F.nx) * ch, cw + .6, ch + .6, { fill: on ? (r < .01 ? C.hi : g.ramp(1 - .5 * r / TOP, COOL)) : g.ramp(.3 * q / F.max, COOL), alpha: on ? 1 : .5 }); });
  const sy = y0 + hgt + g.fs(2), sx0 = x0 + w * .04, sx1 = x0 + w * .96, SX = v => sx0 + (sx1 - sx0) * v / TOP;
  g.line(sx0, sy, sx1, sy, { color: C.line, w: 5 }); g.line(sx0, sy, SX(share), sy, { color: C.hi, w: 5 });
  [.01, .05, .1, .2].forEach(v => { g.line(SX(v), sy - 7, SX(v), sy + 7, { color: C.mute }); g.text(Math.round(v * 100) + "%", SX(v), sy + g.fs(1.4), { align: "center", color: C.mute, size: .82 }); });
  g.dot(SX(share), sy, 9, C.hi); g.ring(SX(share), sy, 9, C.bg, 2);
  const lab = share < .0995 ? (share * 100).toFixed(1) : String(Math.round(share * 100));
  g.text("best " + lab + "% of Earth", x0, sy + g.fs(3.4), { weight: 600, color: C.hi, size: 1.05 });
  g.text(g.narrow ? "gold: best 1%" : "gold: the best 1% · blue: the rest of the band", x0 + w, sy + g.fs(3.4), { align: "right", color: C.mute, size: .85 });
}
function sPatches(g, t) {
  const { C } = g, F = fieldRank(), SH = .2, P = fieldPatches(SH), n = g.narrow;
  head(g, "Cells that touch are one place");
  const x0 = g.X(.06), w = Math.min(g.W * .88, g.H * .6 * F.nx / F.ny), y0 = g.Y(.16), cw = w / F.nx, hgt = w * F.ny / F.nx, ch = hgt / F.ny;
  F.f.forEach((q, i) => g.rect(x0 + (i % F.nx) * cw, y0 + Math.floor(i / F.nx) * ch, cw + .6, ch + .6, { fill: g.ramp(.3 * q / F.max, COOL), alpha: .5 }));
  const shown = P.slice(0, 6), tot = P.reduce((a, q) => a + q.cells.length, 0);
  shown.forEach((q, k) => {
    const a = g.seg(t, .08 + k * .12, .2 + k * .12);
    q.cells.forEach(c => g.rect(x0 + (c % F.nx) * cw, y0 + Math.floor(c / F.nx) * ch, cw + .6, ch + .6, { fill: g.ramp(1 - .5 * F.rank[c] / SH, COOL), alpha: a }));
  });
  shown.forEach((q, k) => {
    const a = g.seg(t, .14 + k * .12, .26 + k * .12), b = q.best, px = x0 + (b % F.nx + .5) * cw, py = y0 + (Math.floor(b / F.nx) + .5) * ch;
    g.dot(px, py, g.fs(.95), C.hi, a); g.text(String(k + 1), px, py + 1, { align: "center", color: C.bg, weight: 700, alpha: a, size: .95 });
    if (!n) g.text(q.cells.length + " cells", px + g.fs(1.4), py - g.fs(1.2), { color: C.ink, weight: 600, alpha: a, size: .82 });
  });
  g.text(tot + " cells in the band  →  " + P.length + " places on the list", x0 + w / 2, y0 + hgt + g.fs(2), { align: "center", weight: 600, color: C.hi, alpha: g.seg(t, .85, 1), size: n ? .88 : 1 });
}

/* ---------------------------------------------------------------- 9 describe */
function sDescribe(g, t) {
  const { C } = g, rows = DATA.pair, x0 = g.X(g.narrow ? .36 : .25), x1 = g.X(g.narrow ? .8 : .66), top = g.Y(.2), rh = g.H * .087, vc = { agrees: C.good, partial: C.mute, differs: C.bad };
  head(g, "Describe each site, variable by variable");
  g.dot(g.X(.06), g.Y(.125), 5, C.earth); g.text("an Earth cell (Dry Valleys, Antarctica)", g.X(.06) + 12, g.Y(.125), { size: .85, color: C.mute });
  if (!g.narrow) { g.rect(g.X(.52), g.Y(.125) - 5, 10, 10, { fill: C.hi, r: 2 }); g.text("the target (Haworth)", g.X(.52) + 18, g.Y(.125), { size: .85, color: C.mute }); }
  rows.forEach((r, i) => {
    const a = g.seg(t, i * .08, i * .08 + .2), m = g.seg(t, i * .08 + .1, i * .08 + .4), y = top + rh * (i + .5), X = p => x0 + (x1 - x0) * p, pe = g.lerp(.5, r.pe, m), pt = g.lerp(.5, r.pt, m);
    g.text(r.name, x0 - 12, y, { align: "right", alpha: a, size: g.narrow ? .82 : .95 });
    const lim = r.ranked === false;
    g.line(x0, y, x1, y, { color: C.line, w: 4, alpha: a }); g.line(X(pe), y, X(pt), y, lim ? { color: C.mute, w: 2, alpha: a, dash: [4, 4] } : { color: vc[r.verdict], w: 4, alpha: a });
    g.dot(X(pe), y, 6, C.earth, a); g.rect(X(pt) - 5, y - 5, 10, 10, { fill: C.hi, r: 2, alpha: a });
    g.text(lim ? (g.narrow ? "limit" : "Earth's limit") : r.verdict, x1 + 14, y, { color: lim ? C.hi : vc[r.verdict], weight: 600, alpha: g.seg(t, i * .08 + .35, i * .08 + .5), size: g.narrow ? .82 : .95 });
    const nf = v => Math.abs(v) >= 100 ? fmt(v) : Number(v).toPrecision(3);
    if (!g.narrow) g.text(nf(r.earth) + r.unit + "  vs  " + nf(r.target) + r.unit, x1 + g.W * (lim ? .115 : .09), y, { color: C.mute, alpha: g.seg(t, i * .08 + .35, i * .08 + .5), size: .85 });
  });
  g.text("0", x0, top + rh * 8.4, { align: "center", color: C.mute, size: .8 }); g.text("position on the shared scale", (x0 + x1) / 2, top + rh * 8.4, { align: "center", color: C.mute, size: .8 }); g.text("1", x1, top + rh * 8.4, { align: "center", color: C.mute, size: .8 });
}

/* ---------------------------------------------------------------- 11 output */
function sOutput(g, t) {
  const { C } = g, bx = boxes(g, 2, { top: .15, bot: .93 }), A = bx[0], B = bx[1];
  head(g, "What the user sees, and what Earth cannot offer");
  const a = g.seg(t, 0, .25); g.rect(A.x, A.y, A.w, A.h, { fill: C.panel, stroke: C.line, r: 10, alpha: a });
  const px = A.x + A.w * .07; g.text("Site 1", px, A.y + A.h * .13, { weight: 700, size: 1.2, display: true, alpha: a });
  [["terrain", .82, C.earth], ["composition", .6, C.moon], ["thermal", null, C.mute]].forEach((r, i) => {
    const y = A.y + A.h * (.27 + i * .14), m = g.seg(t, .2 + i * .1, .5 + i * .1);
    g.text(r[0], px, y, { alpha: a, size: .9, color: r[1] == null ? C.mute : C.ink });
    if (r[1] == null) { g.text(g.narrow ? "beyond Earth's range" : "beyond Earth's range · shown as a limit", px + A.w * .32, y, { color: C.mute, alpha: a * m, size: .85 }); return; } g.rect(px + A.w * .32, y - g.fs(.5), A.w * .52, g.fs(1), { fill: C.line, r: 4, alpha: a }); g.rect(px + A.w * .32, y - g.fs(.5), A.w * .52 * r[1] * m, g.fs(1), { fill: r[2], r: 4, alpha: a });
  });
  g.text("good for: mobility tests on these slopes", px, A.y + A.h * .74, { color: C.good, weight: 600, alpha: g.seg(t, .5, .7), size: g.narrow ? .78 : .88 });
  g.text("not for: long-traverse planning", px, A.y + A.h * .83, { color: C.bad, weight: 600, alpha: g.seg(t, .55, .75), size: g.narrow ? .78 : .88 });
  g.text("against chance: p printed as it comes out", px, A.y + A.h * .93, { color: C.mute, alpha: g.seg(t, .6, .8), size: g.narrow ? .74 : .82 });
  const lim = [["Gravity", "one sixth on the Moon; Earth cannot copy it"], ["Air", "none on the Moon, thin on Mars"], ["Radiation", "Earth's air and magnetic field block it"], ["Temperature", "measured: " + Math.round(DATA.num.ranking.limits[0].gap) + " K colder than Earth's coldest ground"]];
  g.text("Earth's limits", B.x, B.y + B.h * .06, { weight: 700, size: 1.2, display: true, alpha: g.seg(t, .45, .6) });
  lim.forEach((l, i) => { const al = g.seg(t, .55 + i * .09, .7 + i * .09), y = B.y + B.h * (.22 + i * .2); g.text(l[0], B.x, y, { weight: 600, color: i === 3 ? C.hi : C.ink, alpha: al }); g.text(l[1], B.x, y + g.fs(1.35), { color: C.mute, alpha: al, size: g.narrow ? .8 : .88 }); });
}
function sPipeline(g, t) {
  const { C } = g, names = ["Grid", "Variables", "One scale", "Whitening", "Target", "Score every cell", "Test against chance", "Pick sites", "Describe", "Output"];
  head(g, "The whole method in one line");
  const cols = g.narrow ? 2 : 4, cw = g.W * .9 / cols, rh = g.H * (g.narrow ? .125 : .2);
  names.forEach((nm, i) => {
    const a = g.seg(t, i * .075, i * .075 + .15), c = i % cols, r = Math.floor(i / cols), x = g.X(.05) + cw * c, y = g.Y(.17) + rh * r, w = cw * .88, h = rh * .66;
    g.rect(x, y, w, h, { fill: C.panel, stroke: a > .5 ? C.hi : C.line, r: 8, alpha: .35 + .65 * a, w: 2 });
    g.text(String(i + 1), x + 12, y + h / 2, { color: C.hi, weight: 700, alpha: a, size: 1.05 }); g.text(nm, x + 12 + g.fs(1.7), y + h / 2, { weight: 600, alpha: .4 + .6 * a, size: g.narrow ? .82 : .95 });
  });
  g.text("Later: check how the answer moves when the group weights change.", g.X(.5), g.Y(g.narrow ? .86 : .84), { align: "center", color: C.mute, alpha: g.seg(t, .85, .95), size: g.narrow ? .78 : .92 });
  g.text("Every number can be traced back to public data.", g.X(.5), g.Y(.94), { align: "center", color: C.hi, weight: 600, alpha: g.seg(t, .92, 1), size: g.narrow ? .85 : 1 });
}

/* ---------------------------------------------------------------- the list */
const STEPS = [
  { ch: "The question", dur: 5200, title: "Where on Earth is most like a place on the Moon or Mars?", text: "Before a rover or a crew goes there, we want to practise somewhere similar on Earth. A place like that is called an analog. Our tool takes a region on the Moon or Mars and searches all of Earth's land for the closest matches.", draw: sQuestion },
  { ch: "1 · Grid", dur: 4200, title: "Problem: the data does not line up", text: "Elevation comes as a point every half kilometre. Temperature comes in 5 km squares. Lunar chemistry comes in 60 km blocks. Rock maps are drawn shapes. You cannot compare a place on one map with a place on another until they share the same cells.", draw: sSizes },
  { ch: "1 · Grid", dur: 6500, title: "An ordinary map grid is unfair near the poles", text: "On a latitude and longitude grid, a cell near the pole covers 7.6 times less ground than one at the equator. The Artemis landing regions sit right at the Moon's south pole. So we use a grid whose cells all cover the same area.", draw: sShrink },
  { ch: "1 · Grid", dur: 4500, title: "The same size of cell on all three worlds", text: "Earth, Mars and the Moon each get a different number of cells, chosen so that one cell is about 6 to 7 km across everywhere. A crater on the Moon and a valley on Earth are measured with the same ruler.", draw: sRuler },
  { ch: "1 · Grid", dur: 5200, title: "Filling a cell", text: "If the data is finer than a cell, we average it. If it is coarser, the cell copies the value, and we record that it is a copy. If it is a category such as a rock type, the class covering most of the cell wins.", draw: sFill },
  { ch: "2 · Variables", dur: 6500, title: "What do we measure? First, the shape of the ground", text: "Slope says how steep the ground is. Roughness says how much the height changes inside a window around the cell. We measure roughness four times, with windows from 5 km to 42 km, because small bumps and big ones matter to different things.", draw: sSlope },
  { ch: "2 · Variables", dur: 6500, title: "Bowls, ridges and open sky", text: "Landform position compares a cell with its surroundings: lower means a bowl, higher means a ridge. Sky view says how much of the sky is not hidden by terrain. On a crater floor both are low, which is why some lunar craters never see the Sun.", draw: sBowl },
  { ch: "2 · Variables", dur: 5500, title: "Then heat and rock", text: "Temperature level is the average. The day–night swing is how far it moves in a day; on Mars we also use the swing over a year. Silica and iron oxide describe the rock: granite-like ground is rich in silica, basalt-like ground is rich in iron.", draw: sThermal },
  { ch: "2 · Variables", dur: 5200, title: "The result is a cube of layers", text: "Every variable becomes one layer, and every layer uses the same cells. These dots are real: Earth's land coloured by roughness, then by temperature. The search never goes back to the raw files. It reads only this cube.", draw: sCube },
  { ch: "3 · One scale", dur: 8000, title: "Put both worlds on one scale", text: "Metres, kelvin and percent cannot be added together, so every variable is turned into a position between 0 and 1. Take the smallest value found on either world and call it 0. Take the largest and call it 1. Everything else lands in between, on a straight line, so equal differences stay equal. A value lands at the same position whichever world it comes from. Earth's middle cell sits at 0.01 and the Moon's at 0.14: the Moon really is ten times rougher.", draw: sPooled },
  { ch: "3 · One scale", dur: 7500, title: "The scale also shows what Earth cannot offer", text: "On temperature, Earth and the Moon do not overlap. Haworth is about 100 K colder than the coldest ground on Earth. That gap is reported on every result, in kelvin: it is where the analogy breaks down. Should such a variable also help to rank Earth's places? We built both versions and ran them side by side. Our main result counts every variable; the second view leaves out what Earth cannot reach.", draw: sNoOverlap },
  { ch: "4 · Whitening", dur: 6000, title: "Problem: some variables say the same thing twice", text: "Each dot is a real Earth cell. Steep places are usually rough, so the cloud is a tilted streak. Candidate A and candidate B are equally far from the target by plain ruler. But A follows the usual pattern, and B goes against it.", draw: (g, t) => { head(g, "Slope and roughness move together"); sWhitenA(g, t, 0); } },
  { ch: "4 · Whitening", dur: 6500, title: "Solution: measure how surprising a difference is", text: "We learn the usual pattern from Earth and stretch the picture until the cloud is round. This is called whitening. Everything is now measured in units of Earth's own spread. A's difference was expected, so it shrinks. B's difference was unusual, so it grows. Distance measured this way is the Mahalanobis distance. Nothing is counted twice any more.", draw: sWhitenB },
  { ch: "4 · Whitening", dur: 5500, title: "Keep the three groups apart", text: "The correction is done inside each group separately, so we can always say which group disagrees. Eight terrain variables turn out to be worth about four independent pieces of information. Between two Earth cells, terrain carries about half of the difference.", draw: sGroups },
  { ch: "5 · Target", dur: 6500, title: "Now pick a place", text: "This is the Moon's south pole, drawn from our cube: each small square is one cell, coloured by temperature. The outlines are the nine regions NASA is considering for the Artemis III landing. A user can also draw their own area.", draw: sPole },
  { ch: "5 · Target", dur: 6000, title: "The target is its cells, not an average", text: "Selecting Haworth picks the 15 cells whose centres lie inside it. We keep all 15, each with its 12 numbers, and never blend them into one average cell. Ten of the numbers are within Earth's range. The two temperature numbers are beyond anything on Earth.", draw: sSelect },
  { ch: "6 · Score", dur: 6500, note: "Two of the ranking variables · real positions", title: "Put Earth and the target in the same space", text: "Here are two of the variables that rank Haworth: roughness and landform position, in units of Earth's own spread. Blue dots are real Earth cells. Yellow squares are Haworth's real cells. They sit far to the right, rougher than almost all of Earth, and they are spread out: rim, slope and floor are different ground. In the real method this space has ten or twelve directions, not two.", draw: (g, t) => { head(g, "Earth cells and target cells, side by side"); sSpace(g, t, 0); } },
  { ch: "6 · Score", dur: 7000, note: "Illustration · two variables", title: "Score one Earth cell", text: "Take one Earth cell. Measure its distance to every one of the 15 target cells and average them. That is its score. A low score means the place is like the region as a whole. No single place can be close to rim, slope and floor at once, so a score is never zero. We read it by rank: who is closest, not how small the number is.", draw: (g, t) => { head(g, "How one cell is scored"); sSpace(g, t, 1); } },
  { ch: "6 · Score", dur: 5500, note: "Illustration · two variables", title: "Score every cell: that is the map", text: "Repeat for all 3.2 million land cells. The result is a map of scores, small where Earth resembles the target and large where it does not. This map is the main output. There is no pass mark and no cut-off anywhere in it. We make it twice: once with every variable, once with only the variables Earth can match. For Haworth each takes less than a second.", draw: (g, t) => { head(g, "All of Earth, scored"); sSpace(g, t, 2); } },
  { ch: "6 · Score", dur: 8000, note: ILLUS, title: "Turn scores into ranks: the best 1%, the best 5%", text: "Line the cells up from best to worst. The map then shows bands: the best 1% of Earth, the best 5%. A slider moves the line. At 1% only one valley lights up. Loosen it and other valleys join. A best 1% always exists, even for a hopeless target, so the chance test in the next step is always shown beside it.", draw: sSlider },
  { ch: "7 · Chance", dur: 7000, note: "Real map · invented scores", title: "Problem: a search always finds something", text: "Search for Haworth and Earth's best match gets some score. But outline any random patch of the Moon, run the same search, and it gets a best match too. Sort three million numbers and one of them is always the smallest.", draw: sAnySearch },
  { ch: "7 · Chance", dur: 8000, note: "Real map · invented scores", title: "Solution: see how often a random patch does as well", text: "We outline 1,000 random patches of the same size, at the same latitude on the same world, and search for each. Every patch adds its best score to the chart. Then we ask where the real target falls. If many random patches matched Earth just as well, the result is not special, and we say so in plain words.", draw: sNull },
  { ch: "7 · Chance", dur: 7500, note: "Illustration", title: "And one check that the test itself works", text: "Before any real target, we give the test a case with a known answer: a patch of the Atacama desert. It is Earth ground, so a perfect match exists on Earth. If the test finds it, the test can see. Then a result of 'not significant' for a real target is a finding. If the test misses it, no result from it can be trusted.", draw: sControl },
  { ch: "8 · Sites", dur: 5500, note: ILLUS, title: "Problem: the best cells are neighbours", text: "Bright cells here are the good matches. If we simply take the 20 best, they land in the same valley, because neighbouring ground is similar. That is one site, not twenty.", draw: (g, t) => sSites(g, t, 0) },
  { ch: "8 · Sites", dur: 7000, note: ILLUS, title: "Solution: cells that touch are one place", text: "Take the cells inside the slider's band. Cells that touch each other are one place, so they become one entry, shown by its best cell and its size. Move the slider and the list follows. Nothing else has to be measured. If all the best cells sit in one valley, the list has one entry, and that is the honest answer.", draw: sPatches },
  { ch: "9 · Describe", dur: 7000, title: "Say where the match holds and where it breaks", text: "For each site we show every variable on the shared scale: the Earth cell and the target. These are real values. The slope agrees because it is the same slope, 7.8° against 7.5°. Temperature is 116 K apart, further than anything on Earth can close, so it is marked as Earth's limit. Both facts go in the answer.", draw: sDescribe },
  { ch: "10 · Output", dur: 7000, note: "Illustration · layout only", title: "The answer, with its limits attached", text: "Each site comes with a score per group and three plain lists: what it is good for, what it must not be used for, and what no place on Earth can offer. The chance test is printed as it comes out, significant or not. Every result page also states what Earth cannot reproduce. For temperature that is no longer an opinion: we measured it.", draw: sOutput },
  { ch: "10 · Output", dur: 6500, title: "Ten steps, one chain", text: "Line the data up. Measure the ground. Put both worlds on one scale. Remove double counting. Choose a target. Score every cell. Test against chance. Pick the sites. Describe each one. Report it, limits included.", draw: sPipeline },
];
