// The terminal "Copy to clipboard" helpers from gui_installer/status_page.html (between "terminal copy (begin)" and "(end)") under node,
// plus a check that every terminal window of the page has its button.
//   node test_tools/terminal_copy_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- terminal copy (begin) ----');
const b = html.indexOf('// ---- terminal copy (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { terminalText };')();
let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }
const el = (text, cls) => ({ innerText: text, classList: { contains: (c) => c === cls } });

ok(T.terminalText(el('line 1\nline 2\n\n', '')) === 'line 1\nline 2', 'the whole text, trailing blank lines trimmed');
ok(T.terminalText(el('Terminal output will appear here', 'log-placeholder')) === '', 'the placeholder sentence is not output');
ok(T.terminalText(null) === '', 'no element: nothing');
ok(T.terminalText({ textContent: 'only textContent', classList: { contains: () => false } }) === 'only textContent', 'falls back to textContent');

for (const id of ['log', 'mb-log', 'last-run-banner-log']) {
  ok(new RegExp('copyTerminal\\(\'' + id + '\', this\\)').test(html), 'terminal #' + id + ' has a Copy to clipboard button');
  ok(html.indexOf('id="' + id + '"') < html.indexOf("copyTerminal('" + id + "'"), 'the button for #' + id + ' sits below the terminal');
}

// Multi-Point Alignment lives in the Quick Actions tile: its title on the right of the Threshold row, its settings right below, no divider bar
const row = html.indexOf('id="mb-threshold-manual-row"');
const toggle = html.indexOf('id="mb-mpa-toggle"');
const details = html.indexOf('id="mb-multialign-details"');
const coupling = html.indexOf('id="mb-coupling-row"');
ok(row > 0 && toggle > row && toggle < html.indexOf('</div>', html.indexOf('id="mb-decouple-btn"')) + 400, 'the Multi-Point Alignment title sits in the Threshold row');
ok(details > toggle && details < coupling, 'its settings open inside the Quick Actions tile, before the Coupling tile');
ok(!/class="collapsible-toggle"[^>]*multialign/.test(html), 'no separate divider-style toggle for it any more');
process.exit(failed ? 1 : 0);
