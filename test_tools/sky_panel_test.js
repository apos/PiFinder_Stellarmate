// Runs the Sky Position Panel's pure functions from gui_installer/status_page.html
// (the block between "Sky Position Panel (begin)" and "(end)") under node, no browser.
//   node test_tools/sky_panel_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- Sky Position Panel (begin) ----');
const b = html.indexOf('// ---- Sky Position Panel (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
let code = html.slice(a, b);
code = code.replace(/setInterval\([\s\S]*?\}, 2000\);\n/, '');  // no timer under test

// minimal DOM stand-in that records what is drawn
function mkEl(name) {
  return { name, attrs: {}, children: [], _text: '',
    setAttribute(k, v) { this.attrs[k] = v; }, appendChild(c) { this.children.push(c); },
    set textContent(t) { this._text = t; if (t === '') this.children = []; }, get textContent() { return this._text; } };
}
const document = { createElementNS: (ns, n) => mkEl(n), getElementById: () => null };
const sandbox = new Function('document', code + '\nreturn { skyPlace, skySep, skyBuildModel, drawSkyPanel, SKY_CX, SKY_CY, SKY_R };');
const T = sandbox(document);

let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }
function overlap(m1, m2) {
  const box = (m) => { const w = m.name.length * 6.9, x = m.label.x;
    const x0 = m.label.anchor === 'end' ? x - w : m.label.anchor === 'middle' ? x - w / 2 : x;
    return { x0, x1: x0 + w, y0: m.label.y - 10, y1: m.label.y + 3 }; };
  const p = box(m1), q = box(m2);
  return !(p.x1 < q.x0 || p.x0 > q.x1 || p.y1 < q.y0 || p.y0 > q.y1);
}
const pt = (alt, az, stale) => ({ alt, az, below: alt < 0, stale: !!stale });
const mk = (o) => Object.assign({ location_known: true, lat: 49.4, lon: 8.6, mount: null, mount_state: null, pifinder: null, goto: null, held: null }, o);
const find = (m, id) => m.markers.find((x) => x.id === id);

// projection: north up, east left, zenith in the middle, below the horizon outside the rim
let p = T.skyPlace(pt(45, 0)); ok(p.y < T.SKY_CY && Math.abs(p.x - T.SKY_CX) < 1e-6, 'north (az 0) is above the centre');
p = T.skyPlace(pt(45, 90)); ok(p.x < T.SKY_CX && Math.abs(p.y - T.SKY_CY) < 1e-6, 'east (az 90) is left of the centre');
p = T.skyPlace(pt(45, 270)); ok(p.x > T.SKY_CX, 'west (az 270) is right of the centre');
p = T.skyPlace(pt(45, 180)); ok(p.y > T.SKY_CY, 'south (az 180) is below the centre');
p = T.skyPlace(pt(90, 123)); ok(Math.abs(p.x - T.SKY_CX) < 1e-6 && Math.abs(p.y - T.SKY_CY) < 1e-6, 'zenith is the centre');
p = T.skyPlace(pt(0, 0)); ok(Math.abs(Math.hypot(p.x - T.SKY_CX, p.y - T.SKY_CY) - T.SKY_R) < 1e-6, 'horizon is the rim');
p = T.skyPlace(pt(-14, 328)); ok(p.below && Math.hypot(p.x - T.SKY_CX, p.y - T.SKY_CY) > T.SKY_R, 'below the horizon sits outside the rim');

// states
ok(T.skyBuildModel(null) === null, 'no sky data: no tile');
let m = T.skyBuildModel(mk({ location_known: false }));
ok(m.unknown === true && m.markers.length === 0, 'location unknown: no markers at all');
m = T.skyBuildModel({ location_known: false, mount: pt(90, 0), pifinder: pt(90, 0) });
ok(m.unknown === true && m.markers.length === 0, 'location unknown never plots an altitude of 90');

// today's case: mount not tracking, PiFinder 14 deg below the horizon
m = T.skyBuildModel(mk({ mount: pt(50, 97), mount_state: 'not tracking', pifinder: pt(-14.4, 327.9) }));
ok(find(m, 'mount').name === 'Mount (stopped)' && find(m, 'mount').color === '#f5a623', 'not tracking: yellow "Mount (stopped)"');
ok(find(m, 'pifinder').name === 'PiFinder −14°', 'below horizon: name carries the altitude');
ok(m.line.color === '#e53935', 'below horizon: red line');
ok(m.line.arrow && m.line.arrow.from === find(m, 'pifinder').p && m.line.arrow.to === find(m, 'mount').p, 'arrow starts at the one below the horizon (PiFinder) and points to the mount: Sync PiFinder from mount');
// reverse: the mount below, PiFinder fine
m = T.skyBuildModel(mk({ mount: pt(-5, 97), mount_state: 'tracking', pifinder: pt(40, 100) }));
ok(m.line.arrow && m.line.arrow.from === find(m, 'mount').p && m.line.arrow.to === find(m, 'pifinder').p, 'arrow starts at the mount and points to PiFinder when the mount is the one below the horizon');
// just below the horizon: one decimal instead of "-0"
m = T.skyBuildModel(mk({ mount: pt(50, 97), pifinder: pt(-0.4, 327.9) }));
ok(find(m, 'pifinder').name === 'PiFinder −0.4°', 'a few tenths below the horizon shows one decimal, not -0');
m = T.skyBuildModel(mk({ mount: pt(50, 97), pifinder: pt(-14.4, 327.9) }));
ok(find(m, 'pifinder').name === 'PiFinder −14°', 'further below the horizon stays whole degrees');
// both below: no arrow
m = T.skyBuildModel(mk({ mount: pt(-5, 97), pifinder: pt(-20, 100) }));
ok(m.line.arrow === null && m.line.color === '#e53935', 'both below: red line, no arrow');
// both agree, both names still shown, no overlap
m = T.skyBuildModel(mk({ mount: pt(52, 190), mount_state: 'tracking', pifinder: pt(52.6, 188) }));
ok(find(m, 'mount') && find(m, 'pifinder') && m.line.color === '#4caf50' && m.line.arrow === null, 'agree: both markers, green line, no arrow');
ok(find(m, 'mount').name === 'Mount (tracking)' && find(m, 'mount').color === '#4caf50', 'tracking: green "Mount (tracking)"');
ok(!overlap(find(m, 'mount'), find(m, 'pifinder')), 'agree: the two names do not overlap');
// far apart, both visible: yellow, no arrow (only the user can know)
m = T.skyBuildModel(mk({ mount: pt(35, 150), mount_state: 'tracking', pifinder: pt(62, 235) }));
ok(m.line.color === '#f5a623' && m.line.arrow === null, 'far apart: yellow line, no arrow');
// names never sit on a marker symbol (the screenshot case: mount and PiFinder almost on one spot)
{
  const lbox = (mm) => { const w = mm.name.length * 6.9, x = mm.label.x;
    const x0 = mm.label.anchor === 'end' ? x - w : mm.label.anchor === 'middle' ? x - w / 2 : x;
    return { x0, x1: x0 + w, y0: mm.label.y - 10, y1: mm.label.y + 3 }; };
  const cases = [
    mk({ mount: pt(60, 255), mount_state: 'not tracking', pifinder: pt(62, 250) }),
    mk({ mount: pt(60, 255), mount_state: 'tracking', pifinder: pt(60.5, 255.5), goto: pt(61, 256), held: pt(59, 254) }),
    mk({ mount: pt(85, 10), mount_state: 'tracking', pifinder: pt(86, 12) }),
    mk({ mount: pt(5, 30), mount_state: 'parked', pifinder: pt(-4, 32) }),
  ];
  cases.forEach((c, n) => {
    const mm = T.skyBuildModel(c);
    let bad = 0;
    mm.markers.forEach((a) => mm.markers.forEach((b) => {
      const sy = { x0: b.p.x - 5, x1: b.p.x + 5, y0: b.p.y - 5, y1: b.p.y + 5 }, lb = lbox(a);
      if (!(lb.x1 < sy.x0 || lb.x0 > sy.x1 || lb.y1 < sy.y0 || lb.y0 > sy.y1)) bad++;
    }));
    ok(bad === 0, 'case ' + (n + 1) + ': no name covers a marker symbol');
  });
}
// parked
m = T.skyBuildModel(mk({ mount: pt(53, 119), mount_state: 'parked', pifinder: pt(53.4, 120) }));
ok(find(m, 'mount').name === 'Mount (parked)' && find(m, 'mount').color === '#e53935', 'parked: red "Mount (parked)"');
m = T.skyBuildModel(mk({ mount: pt(53, 119), mount_state: null, pifinder: pt(53.4, 120) }));
ok(find(m, 'mount').name === 'Mount', 'unknown mount state: plain "Mount"');
// no mount (Dobsonian): PiFinder and Goto only, no line
m = T.skyBuildModel(mk({ pifinder: pt(40, 60), goto: pt(58, 105) }));
ok(!find(m, 'mount') && find(m, 'pifinder') && find(m, 'goto') && m.line === null, 'no mount: PiFinder and Goto, no line');
// Goto and Held with mount and PiFinder on the same spot: all four names, none overlapping
m = T.skyBuildModel(mk({ mount: pt(55, 205), mount_state: 'tracking', pifinder: pt(55.4, 204), held: pt(55.2, 205), goto: pt(30, 120) }));
const ids = m.markers.map((x) => x.id).sort().join(',');
ok(ids === 'goto,held,mount,pifinder', 'goto and held are drawn');
let clash = false; for (let i = 0; i < m.markers.length; i++) for (let j = i + 1; j < m.markers.length; j++) if (overlap(m.markers[i], m.markers[j])) clash = true;
ok(!clash, 'four names around coincident markers do not overlap');
// stale position is flagged
m = T.skyBuildModel(mk({ pifinder: pt(40, 60, true) }));
ok(find(m, 'pifinder').stale === true, 'stale (last known) position is flagged');

// a missing position says so instead of silently not appearing
m = T.skyBuildModel(mk({ mount: pt(50, 97), mount_state: 'tracking', mount_configured: true }));
ok(find(m, 'mount') && !find(m, 'pifinder') && m.notes.join('|') === 'PiFinder: no position', 'PiFinder without position: note "PiFinder: no position"');
m = T.skyBuildModel(mk({ pifinder: pt(40, 60), mount_configured: true }));
ok(m.notes.join('|') === 'Mount: no position', 'configured mount without position: note "Mount: no position"');
m = T.skyBuildModel(mk({ pifinder: pt(40, 60), mount_configured: false }));
ok(m.notes.length === 0, 'no mount configured (Dobsonian): no mount note');
m = T.skyBuildModel(mk({ mount_configured: true }));
ok(m.notes.length === 2 && m.markers.length === 0, 'nothing known: both notes, no markers');
const nv = mkEl('svg'); T.drawSkyPanel(nv, m);
ok(nv.children.filter((c) => c.name === 'text').map((c) => c._text).includes('PiFinder: no position'), 'drawing writes the note');

// drawing runs and writes every name
const svg = mkEl('svg');
T.drawSkyPanel(svg, T.skyBuildModel(mk({ mount: pt(50, 97), mount_state: 'not tracking', pifinder: pt(-14.4, 327.9) })));
const texts = svg.children.filter((c) => c.name === 'text').map((c) => c._text);
ok(texts.includes('Mount (stopped)') && texts.includes('PiFinder −14°') && ['N', 'E', 'S', 'W'].every((d) => texts.includes(d)), 'drawing contains the names and the four directions');
const u = mkEl('svg'); T.drawSkyPanel(u, T.skyBuildModel(mk({ location_known: false })));
ok(u.children.some((c) => c._text === 'Location unknown'), 'drawing for unknown location says so');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all sky panel tests passed');
