// The two things the page must not hide: a Mount Bridge that reads nothing (red) and its open question (yellow card).
// Runs the functions of gui_installer/status_page.html between "Bridge problems (begin)" and "(end)" under node:
//   node test_tools/bridge_problems_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- Bridge problems (begin) ----');
const b = html.indexOf('// ---- Bridge problems (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { bridgeProblems, bridgeProblemCards };')();

let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }

const base = { running: true, binding_state: 'Ok', binding_missing: null, reposition_question: false, drift_arcmin: 0.4 };
const none = T.bridgeProblems(base);
ok(none.blind === null && none.question === null && T.bridgeProblemCards(none.blind, none.question).length === 0, 'all well: no card');
ok(T.bridgeProblems({ ...base, binding_state: 'Busy', binding_missing: 'Telescope Simulator' }).blind === null, 'still waiting for the devices is not yet a fault');
const blind = T.bridgeProblems({ ...base, binding_state: 'Alert', binding_missing: 'Telescope Simulator' });
const bc = T.bridgeProblemCards(blind.blind, blind.question);
ok(bc.length === 1 && bc[0].tone === 'bad' && bc[0].title.includes('Telescope Simulator') && bc[0].text.includes('What to do'), 'blind: a red card that names the device and says what to do');
const q = T.bridgeProblems({ ...base, reposition_question: true, drift_arcmin: 185 });
const qc = T.bridgeProblemCards(q.blind, q.question)[0];
ok(qc.title === 'Mount and PiFinder suddenly differ by 3°' && !qc.tone, 'question: yellow card with the distance');
ok(qc.text.includes('moves nothing until you decide') && qc.text.includes('What to do'), 'question: says that nothing moves and what to do');
ok(qc.buttons.length === 2 && /Adopt/.test(qc.buttons[0].label) && /slews/.test(qc.buttons[1].label), 'question: both answers, the moving one says so');
ok(T.bridgeProblems({ running: false, binding_state: 'Alert', reposition_question: true }).blind === null, 'no Bridge: nothing to report');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all bridge problem tests passed');
