// "How the search works": the player for the method scenes (js/method/scenes.js, js/method/data.js).
// It replaces the script of docs/explainer/index.html: same STEPS list, same drawing helpers (G), in the site's look.
(function () {
  const root = document.getElementById('method'), cv = document.getElementById('methodCanvas'), ctx = cv.getContext('2d');
  const el = (id) => document.getElementById(id);
  const css = getComputedStyle(document.documentElement), tok = (n) => css.getPropertyValue(n).trim();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let W = 0, H = 0, dpr = 1, idx = 0, t0 = 0, visible = false, started = false;

  // the palette the scenes draw with, from the design system (design_system.md, section 8)
  const C = { bg: tok('--surface-1'), panel: tok('--surface-2'), line: tok('--outline-2'), ink: tok('--on-surface'), mute: tok('--on-surface-2'),
    hi: tok('--answer'), earth: '#8AB4F8', moon: tok('--on-surface-2'), mars: '#E8A87C', good: tok('--on-surface'), bad: tok('--on-surface-2'), beyond: tok('--beyond') };   // earth: a calmer blue for clouds of dots
  const SANS = tok('--f-sans'), MONO = tok('--f-mono');
  const pen = (w) => Math.min(w || 1.2, 2);   // no heavy strokes

  function resize() {
    const r = cv.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2); W = r.width; H = r.height;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  }
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const ease = (t) => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const G = {
    get W() { return W; }, get H() { return H; }, get C() { return C; }, ctx,
    X: (u) => u * W, Y: (v) => v * H, S: (k) => k * Math.min(W, H),
    get narrow() { return W < 520; },
    fs: (k) => clamp(W / 68, 10.5, 16.5) * k,
    clamp, ease, lerp: (a, b, t) => a + (b - a) * t,
    seg: (t, a, b) => ease(clamp((t - a) / (b - a), 0, 1)),
    lin: (t, a, b) => clamp((t - a) / (b - a), 0, 1),
    rnd: (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); },
    text(str, x, y, o = {}) {
      ctx.save(); ctx.globalAlpha = o.alpha == null ? 1 : o.alpha;
      const num = /^[\d\s.,%×+\-−°]+( ?(K|km|m|wt%))?$/.test(String(str));   // a bare number: set it in the mono face
      ctx.font = `${Math.min(o.weight || 400, 500)} ${G.fs((o.size || 1) * (num ? 0.92 : 1))}px ${num ? MONO : SANS}`;
      ctx.fillStyle = o.color || C.ink; ctx.textAlign = o.align || 'left'; ctx.textBaseline = o.base || 'middle';
      ctx.fillText(str, x, y); ctx.restore();
    },
    line(x1, y1, x2, y2, o = {}) {
      ctx.save(); ctx.globalAlpha = o.alpha == null ? 1 : o.alpha; ctx.strokeStyle = o.color || C.ink;
      ctx.lineWidth = pen(o.w); if (o.dash) ctx.setLineDash(o.dash); ctx.lineCap = 'butt';
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.restore();
    },
    dot(x, y, r, color, alpha) { ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha; ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, Math.max(1.1, r * 0.78), 0, 6.2832); ctx.fill(); ctx.restore(); },
    ring(x, y, r, color, w, alpha) { ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha; ctx.strokeStyle = color; ctx.lineWidth = pen(w); ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.stroke(); ctx.restore(); },
    rect(x, y, w, h, o = {}) {
      ctx.save(); ctx.globalAlpha = o.alpha == null ? 1 : o.alpha;
      const r = Math.min(o.r || 0, 3, Math.abs(w) / 2, Math.abs(h) / 2);   // square corners, as on the rest of the site
      ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, r); else ctx.rect(x, y, w, h);
      if (o.fill) { ctx.fillStyle = o.fill; ctx.fill(); }
      if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = Math.min(o.w || 1, 1.5); ctx.stroke(); }
      ctx.restore();
    },
    poly(pts, o = {}) {
      ctx.save(); ctx.globalAlpha = o.alpha == null ? 1 : o.alpha; ctx.beginPath();
      pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
      if (o.close) ctx.closePath();
      if (o.fill) { ctx.fillStyle = o.fill; ctx.fill(); }
      if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = pen(o.w); ctx.lineJoin = 'round'; ctx.lineCap = 'butt'; ctx.stroke(); }
      ctx.restore();
    },
    arrow(x1, y1, x2, y2, o = {}) {
      G.line(x1, y1, x2, y2, o);
      const a = Math.atan2(y2 - y1, x2 - x1), s = Math.min(o.head || 6, 6);
      G.poly([[x2, y2], [x2 - s * Math.cos(a - .45), y2 - s * Math.sin(a - .45)], [x2 - s * Math.cos(a + .45), y2 - s * Math.sin(a + .45)]], { fill: o.color || C.ink, close: true, alpha: o.alpha });
    },
    ramp(v, stops) {
      v = clamp(v, 0, 1);
      for (let i = 1; i < stops.length; i++) if (v <= stops[i][0]) {
        const a = stops[i - 1], b = stops[i], f = (v - a[0]) / (b[0] - a[0] || 1);
        return `rgb(${[0, 1, 2].map((k) => Math.round(a[1][k] + (b[1][k] - a[1][k]) * f)).join(',')})`;
      }
      return `rgb(${stops[stops.length - 1][1].join(',')})`;
    },
  };

  // The words shown under each scene, in the order of STEPS. They are shorter than the explainer's own captions (docs/explainer),
  // written for a judge who reads each one once. Every number comes from those captions; nothing new is claimed.
  const COPY = [
    ['The variables', 'Every cell gets the same measurements. Terrain: eight variables. Temperature: two, and a third on Mars. Rock: two. The Moon is compared on 12 variables, Mars on up to 13.'],
    ['The grid: HEALPix', 'HEALPix divides a sphere into cells of equal area: a cell at the pole covers the same ground as a cell at the equator. Earth, the Moon and Mars all use it.'],
    ['The number of cells', 'Each world gets its own number of cells, chosen so that one cell is 6 to 7 km across everywhere.'],
    ['Filling a cell', 'Finer data is averaged. Coarser data is copied, and marked as a copy. For classes such as rock type, the class covering most of the cell wins.'],
    ['One cube of 14 layers', 'Each variable is one layer on the same cells. These dots are real: Earth\'s land, coloured by roughness, then by temperature. The search reads only this cube.'],
    ['Min–max scaling: both worlds on one scale', 'Each variable becomes a position from 0 to 1: 0 is the smallest value on either world, 1 the largest. Earth\'s middle cell sits at 0.01 and the Moon\'s at 0.14: the Moon is ten times rougher.'],
    ['Overlap: what Earth cannot reach', 'On temperature, Earth and the Moon do not overlap: Haworth is about 100 K colder than Earth\'s coldest ground. We report that gap on every result. Our main result ranks with every variable; a second view leaves out what Earth cannot reach.'],
    ['The example target: Haworth crater', 'The Moon\'s south pole from our cube, coloured by temperature. The outlines are the nine Artemis III candidate regions. Our example is the region at Haworth crater.'],
    ['A target is its cells, not an average', 'Haworth is 15 cells, each with 12 numbers. We keep them all. Ten of the numbers are within Earth\'s range; the two temperature numbers are beyond it.'],
    ['Earth and the target in one space', 'Two of the ranking variables. Blue dots are real Earth cells. Yellow squares are Haworth\'s cells: rougher than almost all of Earth, and spread out.'],
    ['Distance: the mean distance to every target cell', 'Take one Earth cell. Its score is its mean distance to all 15 target cells. Lower means more like the region as a whole. A score is never zero, so we read ranks, not values.'],
    ['Score every cell: that is the map', 'All 3.2 million land cells are scored. There is no pass mark. We make the map twice: with every variable, and with only the variables Earth can match.'],
    ['Whitening: some variables say the same thing twice', 'Steep ground is usually rough. A and B are equally far from the target by plain ruler, but A follows Earth\'s usual pattern and B goes against it.'],
    ['Whitening gives the Mahalanobis distance', 'We learn the usual pattern from Earth and stretch the space until Earth\'s cloud is round: this is whitening. Distance measured this way is the Mahalanobis distance. A\'s expected difference shrinks, B\'s unusual one grows, and nothing is counted twice.'],
    ['The p-test: a search always finds something', 'Any patch of the Moon, even a random one, gets a best match on Earth. A best match alone proves nothing.'],
    ['The p-test: 1,000 random patches', 'We search for 1,000 random patches of the same size and latitude on the same world. p is the share of them that match Earth at least as well as the target. If p is high, the result is not special, and we say so.'],
    ['The p-test is checked on a known case', 'A patch of the Atacama desert has a known answer: a perfect match exists on Earth. If the test finds it, the test works. If it misses it, no result from it can be trusted.'],
    ['The outputs: the best 1%, the best 5%', 'Cells are ordered from best to worst and shown as bands. A slider moves the line. A best 1% exists for every target, so the p-test is always shown beside it.'],
    ['The outputs: places', 'Touching cells of the best band become one place, shown by its best cell and its size.'],
    ['The outputs for Haworth: variable by variable', 'Every variable is shown for the Earth cell and the target, in real units. Slope agrees: 7.8° against 7.5°. Temperature is 116 K apart: that is Earth\'s limit.'],
    ['The outputs: one place, with its limits', 'Each place shows its distance by group, the variables that agree or differ, and what it can be used for. Earth\'s limits are stated with every result.'],
  ];
  if (COPY.length !== STEPS.length) console.error('method: COPY has ' + COPY.length + ' entries, STEPS has ' + STEPS.length);

  // The scenes come in nine chapters (STEPS[i].ch). The site shows them as four steps: chapters that belong together are merged.
  // The site plays a shorter set than the team's explainer (docs/explainer), in the order the team asked for: distance before whitening,
  // then the p-test, and the example's outputs last.
  const GROUPS = [
    { name: 'Measure both worlds', chapters: ['1 · Variables', '2 · Grid', '3 · Cube'] },
    { name: 'Put them on one scale', chapters: ['4 · One scale'] },
    { name: 'Distance and whitening', chapters: ['5 · Target', '6 · Distance', '7 · Whitening'] },
    { name: 'Test, then read the answer', chapters: ['8 · Chance test', '9 · Example outputs'] },
  ];
  const short = (ch) => ch.replace(/^\d+ · /, '');
  const groupOf = (ch) => { const k = GROUPS.findIndex((g) => g.chapters.includes(ch)); return k < 0 ? GROUPS.length - 1 : k; };
  STEPS.forEach((s) => { if (!GROUPS.some((g) => g.chapters.includes(s.ch))) console.error('method: chapter not in a group: ' + s.ch); });
  const nav = el('methodChapters');
  GROUPS.forEach((g, k) => {
    g.first = STEPS.findIndex((s) => groupOf(s.ch) === k);
    const b = document.createElement('button'); b.type = 'button'; b.className = 'chapter'; b.id = 'chap-' + k;
    b.innerHTML = `<span class="chapter__n">${k + 1}</span><span class="chapter__name">${g.name}<small>${g.chapters.map(short).join(' · ')}</small></span>`;
    b.addEventListener('click', () => go(g.first)); nav.appendChild(b);
  });

  function go(i) {
    idx = clamp(i, 0, STEPS.length - 1); t0 = performance.now(); started = true;
    const s = STEPS[idx];
    const k = groupOf(s.ch);
    el('methodKicker').textContent = `Step ${k + 1} of ${GROUPS.length} · ${GROUPS[k].name} · ${short(s.ch)}`; el('methodTitle').textContent = (COPY[idx] || [s.title])[0]; el('methodText').textContent = (COPY[idx] || [0, s.text])[1];
    el('methodCount').textContent = `${idx + 1} / ${STEPS.length}`;
    el('methodPrev').disabled = idx === 0; el('methodNext').disabled = idx === STEPS.length - 1;
    const tag = el('methodTag'); tag.hidden = !s.note; tag.textContent = s.note || '';
    GROUPS.forEach((g, j) => el('chap-' + j).setAttribute('aria-current', String(j === k)));
  }
  function frame(now) {
    if (visible && started) {
      const s = STEPS[idx], t = reduced ? 1 : clamp((now - t0) / s.dur, 0, 1);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
      G.note = !!s.note;
      try { s.draw(G, t); } catch (e) { G.text('This step could not be drawn: ' + e.message, 16, 24, { color: C.ink }); }
      el('methodBar').style.width = (t * 100) + '%';
    }
    requestAnimationFrame(frame);
  }
  el('methodNext').addEventListener('click', () => go(idx + 1));
  el('methodPrev').addEventListener('click', () => go(idx - 1));
  el('methodReplay').addEventListener('click', () => go(idx));
  root.addEventListener('keydown', (e) => {   // keys work only while the section has the focus, so the page still scrolls normally
    if (e.key === 'ArrowRight') { e.preventDefault(); go(idx + 1); } else if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx - 1); }
    else if (e.key === 'r' || e.key === 'R') go(idx);
  });
  new ResizeObserver(resize).observe(cv);
  // play the first step when the stage is first scrolled into view; draw only while it is on screen
  const first = Math.max(1, parseInt(new URLSearchParams(location.search).get('step') || '1', 10)) - 1;
  new IntersectionObserver((e) => { visible = e[0].isIntersecting; if (visible && !started) go(first); }, { threshold: 0.35 }).observe(cv);
  resize(); go(first); started = false;
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => requestAnimationFrame(frame));
})();
