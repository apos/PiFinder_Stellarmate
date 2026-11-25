// Runs pfScreenBox() from gui_installer/status_page.html (between "OLED mirror size (begin)" and "(end)") under node.
//   node test_tools/oled_mirror_size_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- OLED mirror size (begin) ----');
const b = html.indexOf('// ---- OLED mirror size (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { pfScreenBox };')();
let failed = 0;
const eq = (got, want, msg) => { const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) { failed++; console.error('FAIL: ' + msg + ' got ' + JSON.stringify(got)); } else console.log('ok:   ' + msg); };
eq(T.pfScreenBox(128, 128), { w: 192, h: 192, smooth: false }, 'Rev 3, 128 x 128: 192 px, hard pixels (as before)');
eq(T.pfScreenBox(176, 176), { w: 244, h: 244, smooth: true }, 'Rev 4, 176 x 176: 244 px, smoothed');
eq(T.pfScreenBox(320, 240), { w: 244, h: 183, smooth: true }, '320 x 240 keeps 4:3 (244 x 183)');
eq(T.pfScreenBox(0, 0), null, 'no picture loaded yet: leave the box alone');
eq(T.pfScreenBox(60, 30), { w: 90, h: 45 , smooth: false }, "PiFinder's 60 x 30 placeholder (no screen yet) is not stretched to a square");
if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all ok');
