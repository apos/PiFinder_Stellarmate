// The "Real Hardware + GSC Simulation" tile's pure model from gui_installer/status_page.html (the block between "GSC simulation tile
// (begin)" and "(end)") under node, plus a structure check of the mode tiles in the page.
//   node test_tools/gsc_tile_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- GSC simulation tile (begin) ----');
const b = html.indexOf('// ---- GSC simulation tile (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { gscSimTileModel };')();
let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }
const landings = [{ id: 'off', label: 'none' }, { id: 'typical', label: 'typical (8′ E / 5′ S)' }];
const running = (o) => Object.assign({ available: true, reason: '', running: true, state: 'on', landing: 'typical', device: 'Telescope Simulator', test_mode: true, solve_source: 'CAM', landings }, o);

let m = T.gscSimTileModel(null);
ok(!m.on && !m.pending && m.dot === 'dot-white' && m.sub === 'checking\u2026', 'no data yet: checking');
m = T.gscSimTileModel({ available: false, reason: 'The GSC star catalogue tool (gsc) is not installed.' });
ok(m.locked && !m.on && !m.pending && /gsc/.test(m.sub), 'not available: locked, says why');
m = T.gscSimTileModel({ available: true, running: false, state: 'off', landings });
ok(!m.on && !m.pending && !m.locked && /GSC catalogue/.test(m.sub), 'off: invites to start');

m = T.gscSimTileModel(running({ state: 'on' }));
ok(m.on && !m.pending && m.dot === 'dot-green' && m.sub === 'running, solving the simulated sky', 'on: solving, green');
ok(m.chips.length === 4 && m.chips.every((c) => c.ok), 'on: four checkmarks, all fine');
ok(m.chips[1].text === 'Test Mode on' && m.chips[2].text === 'Solving: CAM', 'on: Test Mode on, solving CAM');
ok(m.chips[3].text === 'Following: Telescope Simulator', 'on: says which mount it follows');
ok(m.landing === 'Landing error of a GoTo: typical (8\u2032 E / 5\u2032 S)', 'running: the landing error in words');

// the contradiction seen live: follower running, Test Mode off after a PiFinder restart. Never "on", never "Test Mode off" as a chip.
m = T.gscSimTileModel(running({ state: 'restoring', test_mode: false, solve_source: 'CAM_FAILED' }));
ok(!m.on && m.pending && m.dot === 'dot-yellow' && m.sub === 'restoring Test Mode', 'Test Mode went off: pending, not on');
ok(m.chips.length === 0 && /switched on again/.test(m.note), 'pending: no contradicting checkmarks, one honest sentence');
m = T.gscSimTileModel(running({ state: 'starting', solve_source: 'CAM_FAILED' }));
ok(!m.on && m.pending && /first solve/.test(m.sub) && m.chips.length === 0, 'no solve yet: starting, pending');
m = T.gscSimTileModel(running({ state: 'waiting', test_mode: null, solve_source: null }));
ok(!m.on && m.pending && m.sub === 'waiting for PiFinder' && /not answering/.test(m.note), 'PiFinder not answering: waiting, pending');
m = T.gscSimTileModel(running({ state: undefined, solve_source: 'CAM' }));
ok(!m.on && m.pending, 'an older server without a state: running counts as starting, never as on');
for (const st of ['starting', 'restoring', 'waiting']) {
  const x = T.gscSimTileModel(running({ state: st }));
  ok(!x.chips.some((c) => /off/.test(c.text)), 'state ' + st + ': no chip says off');
}
ok(T.gscSimTileModel(running({ state: 'on', landing: 'unknown' })).landing === '', 'an unknown landing id shows nothing');

// the page: four tiles, the older two grouped under "Other test modes"
const ids = ['mode-tile-real', 'mode-tile-gsc', 'mode-tile-sim', 'mode-tile-fake', 'gsc-sim-panel', 'gsc-sim-idle', 'gsc-sim-landing', 'gsc-sim-pending'];
ids.forEach((id) => ok(html.includes('id="' + id + '"'), 'page has #' + id));
const posGsc = html.indexOf('id="mode-tile-gsc"'), posOther = html.indexOf('Other test modes</div>'), posSim = html.indexOf('id="mode-tile-sim"'), posFake = html.indexOf('id="mode-tile-fake"');
ok(posGsc > 0 && posGsc < posOther && posOther < posSim && posSim < posFake, 'GSC tile first; Full Simulation and Fake Mode after "Other test modes"');
ok(/class="mode-tile mode-tile-minor" id="mode-tile-sim"/.test(html) && /class="mode-tile mode-tile-minor" id="mode-tile-fake"/.test(html), 'the two older modes are the quiet tiles');
ok(/Start GSC simulation/.test(html) && /No solve active'/.test(html) && !/neither real nor synthetic/.test(html), 'the no-solve message offers the GSC simulation');

// the minor row is closed before the readiness line and the One-Click row (they must not sit between the switches)
const rowStart = html.indexOf('<div class="mode-tiles mode-tiles-minor">'), readiness = html.indexOf('<div id="sim-readiness-line">');
const between = html.slice(rowStart, readiness);
ok((between.match(/<div\b/g) || []).length === (between.match(/<\/div>/g) || []).length, 'the "Other test modes" row is closed before the setup readiness line');
ok(!/mode-tile-new|>new</.test(html.slice(html.indexOf('id="mode-tile-gsc"'), html.indexOf('id="mode-tile-gsc"') + 700)), 'no "new" badge on the GSC tile');

// "Sync PiFinder from mount" without a solve falls back to injecting the mount's position instead of refusing
const syncStart = html.indexOf('async function triggerSyncPiFinderFromMount()');
const syncBody = html.slice(syncStart, html.indexOf('\n}\n', syncStart));
const noSolve = syncBody.slice(syncBody.indexOf("d.reason === 'no_solve'"), syncBody.indexOf("d.reason === 'timeout'"));
ok(/d\.reason === 'no_solve' \|\| d\.reason === 'outside_fov'/.test(syncBody), 'outside the field of view: PiFinder is set to the mount all the same, not just refused');
ok(/await reseedFakeSolve\(\)/.test(noSolve), 'no solve: the mount position is injected (reseedFakeSolve)');
ok(!/Point it at stars/.test(noSolve), 'no solve: no longer sends the user away to point the camera at stars');
ok(/not a camera solve/.test(noSolve), 'no solve: says plainly that this is an injected position, not a camera solve');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all GSC tile tests passed');
