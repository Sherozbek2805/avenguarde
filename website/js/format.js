// Number formatting. The rules are copied from contract/README.md ("Number formatting"): correctness rules, not style.
const minus = (s) => String(s).replace(/^-/, '−');
export const fmtCoord = (x) => minus(Number(x).toFixed(2));                                   // lat, lon: fixed 2 decimals
export const fmtSig3 = (x) => x == null || !isFinite(x) ? 'no data'                           // 3 significant figures
  : minus(new Intl.NumberFormat('en-US', { maximumSignificantDigits: 3 }).format(x));
export const fmtInt = (n) => Math.round(n).toLocaleString('en-US');                          // counts, ranks: integers
export const fmtGap = (x) => x == null || !isFinite(x) ? 'no data' : (x > 0 ? '+' : x < 0 ? '−' : '') + new Intl.NumberFormat('en-US', { maximumSignificantDigits: 3 }).format(Math.abs(x));   // physical_gap: signed, 3 significant figures
export const fmtP = (p, atFloor) => atFloor ? 'p < 0.001' : 'p = ' + Number(Number(p).toPrecision(2));   // p: "p < 0.001" at the floor, else 2 significant figures
export const unit = (u) => u === 'degrees' ? '°' : u === 'dimensionless, 0..1' ? '' : ' ' + u;
