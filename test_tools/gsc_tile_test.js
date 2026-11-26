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
const running = (o) => Object.assign({ available: true, reason: '', running: true, landing: 'typical', device: 'Telescope Simulator', test_mode: true, solve_source: 'CAM', landings }, o);

let m = T.gscSimTileModel(null);
ok(!m.on && m.dot === 'dot-white' && m.sub === 'checking…', 'no data yet: checking');
m = T.gscSimTileModel({ available: false, reason: 'The GSC star catalogue tool (gsc) is not installed.' });
ok(m.locked && !m.on && /gsc/.test(m.sub), 'not available: locked, says why');
m = T.gscSimTileModel({ available: true, running: false, landings });
ok(!m.on && !m.locked && /GSC catalogue/.test(m.sub), 'available but off: invites to start');
m = T.gscSimTileModel(running());
ok(m.on && m.dot === 'dot-green' && m.sub === 'running, solving the simulated sky', 'running and solving: green');
ok(m.chips.length === 4 && m.chips.every((c) => c.ok), 'four chips, all fine');
ok(m.chips[3].text === 'Following: Telescope Simulator', 'says which mount it follows');
ok(m.landing === 'Landing error of a GoTo: typical (8′ E / 5′ S)', 'running: the landing error in words');
m = T.gscSimTileModel(running({ solve_source: 'CAM_FAILED' }));
ok(m.dot === 'dot-yellow' && m.sub === 'running, waiting for the first solve' && !m.chips[2].ok, 'running but not solving yet: yellow');
m = T.gscSimTileModel(running({ test_mode: false }));
ok(m.dot === 'dot-yellow' && m.chips[1].text === 'Test Mode off' && !m.chips[1].ok, 'Test Mode switched off behind its back: yellow');
m = T.gscSimTileModel(running({ test_mode: null, solve_source: null }));
ok(m.chips[1].text === 'Test Mode …' && m.chips[2].text === 'Solving: …', 'PiFinder not answering: dots, not a claim');
ok(T.gscSimTileModel(running({ landing: 'unknown' })).landing === '', 'an unknown landing id shows nothing');

ok(!html.includes('id="gsc-sim-stop-btn"') && !html.includes('Stop simulation') && !html.includes('Stop it to get the real camera back'), 'no second way to stop: Real Hardware is the switch back');
ok(!/class="gsc-sim-chip\b/.test(html) && !html.includes('.gsc-sim-chip {'), 'the status is plain text, not pills that look clickable');

// the page: four tiles, the older two grouped under "Other test modes"
const ids = ['mode-tile-real', 'mode-tile-gsc', 'mode-tile-sim', 'mode-tile-fake', 'gsc-sim-panel', 'gsc-sim-idle', 'gsc-sim-landing'];
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

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all GSC tile tests passed');
