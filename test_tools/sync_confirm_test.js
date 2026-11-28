// Runs the sync confirmation functions of gui_installer/status_page.html (between "Sync confirmation (begin)" and "(end)")
// under node, no browser:   node test_tools/sync_confirm_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- Sync confirmation (begin) ----');
const b = html.indexOf('// ---- Sync confirmation (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { syncConfirmStep, syncApartText, SYNC_CONFIRM_TIMEOUT_S };')();

let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }

let s = T.syncConfirmStep(0.3, 5, 0, 1);
ok(s.state === 'wait' && s.hits === 1, 'one good reading is not yet a confirmation');
s = T.syncConfirmStep(0.3, 5, s.hits, 2);
ok(s.state === 'ok', 'two good readings in a row confirm');
ok(T.syncConfirmStep(600, 5, 1, 3).hits === 0, 'a reading far apart starts the count again');
ok(T.syncConfirmStep(null, 5, 1, 3).state === 'wait', 'no position is no confirmation');
ok(T.syncConfirmStep(600, 5, 0, T.SYNC_CONFIRM_TIMEOUT_S).state === 'fail', 'still apart after the timeout: said so');
ok(T.syncApartText(10630) === '177\u00b0 apart' && T.syncApartText(0.34) === '0.3\u2032 apart' && T.syncApartText(null) === 'no position yet', 'the distance in words');
ok(/await confirmSync\('Mount synced to PiFinder'\)/.test(html) && /await confirmSync\(done, doneHint, doneInjected\)/.test(html), 'both sync directions wait for the confirmation');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all sync confirmation tests passed');
