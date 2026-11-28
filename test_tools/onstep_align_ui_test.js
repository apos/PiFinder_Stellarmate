// What the Multi-Point Alignment tile shows with an OnStep the Mount Bridge reads.
//   node test_tools/onstep_align_ui_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- OnStep alignment (begin) ----');
const b = html.indexOf('// ---- OnStep alignment (end) ----');
if (a < 0 || b < 0) { console.log('FAIL block not found'); process.exit(1); }
const T = new Function(html.slice(a, b) + '\nreturn { onStepAlignView };')();
let failed = 0;
const ok = (c, what) => { console.log((c ? 'ok:   ' : 'FAIL: ') + what); if (!c) failed++; };
const other = T.onStepAlignView(null, false, 4);
ok(other.startLabel === 'Start' && other.confirm === null && !other.saveShown && other.unit === 'point', 'another mount: as before, no question, no Save');
const idle = T.onStepAlignView({ max_stars: 9, star: 0, stars: 0, aligning: false }, false, 3);
ok(/3 stars/.test(idle.confirm) && /home position/.test(idle.confirm) && /replaced/.test(idle.confirm), 'before a start: asks for the home position, names the stars and what is replaced');
ok(idle.saveShown && idle.saveEnabled && idle.startLabel === 'Start' && idle.unit === 'star', 'Save to OnStep available while nothing runs');
ok(/9 stars/.test(T.onStepAlignView({ max_stars: 9, star: 0, stars: 0, aligning: false }, false, 10).confirm), 'never more stars than the controller takes');
ok(/1 star\./.test(T.onStepAlignView({ max_stars: 9, star: 0, stars: 0, aligning: false }, false, 1).confirm), 'one star: singular');
const run = T.onStepAlignView({ max_stars: 9, star: 2, stars: 3, aligning: true }, true, 3);
ok(!run.saveEnabled && run.waiting === null && run.confirm === null, 'during a run: no Save, no waiting text');
const left = T.onStepAlignView({ max_stars: 9, star: 2, stars: 3, aligning: true }, false, 3);
ok(left.startLabel === 'Continue' && left.confirm === null && /star 2 of 3/.test(left.waiting) && !left.saveEnabled, 'an unfinished alignment: Continue, no home question, says where it stands');
ok(T.onStepAlignView({ max_stars: 9, star: 4, stars: 3, aligning: false }, false, 3).saveEnabled, 'finished: Save available');
console.log(failed ? failed + ' failed' : 'all OnStep alignment page tests passed');
process.exit(failed ? 1 : 0);
