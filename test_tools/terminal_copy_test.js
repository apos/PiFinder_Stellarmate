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

// Multi-Point Alignment is a tile like "Sync positions", at the right of the Threshold row; its settings open inside that tile
const row = html.indexOf('id="mb-threshold-manual-row"');
const tile = html.indexOf('id="mb-mpa-tile"');
const details = html.indexOf('id="mb-multialign-details"');
const coupling = html.indexOf('id="mb-coupling-row"');
ok(row > 0 && tile > row && tile < coupling, 'the Multi-Point Alignment tile sits in the Threshold row of the Quick Actions tile');
ok(/class="mb-qa-group mb-mpa-tile"/.test(html), 'it is built like the Sync positions tile (mb-qa-group)');
ok(details > tile && details < coupling, 'its settings open inside that tile');
ok(!/class="collapsible-toggle"[^>]*multialign/.test(html), 'no divider-style toggle for it any more');

// Settings: ONE tile around role, hardware mode, one-click and Web Manager rows; no rule above it or above Setup checklist
const box = html.indexOf('id="mb-settings-box"');
const label = html.indexOf('id="mb-settings-label"');
const setup = html.indexOf("toggleCollapsibleSection('mb-details'");
ok(box > 0 && box < label && label < html.indexOf('id="mode-tile-gsc"') && html.indexOf('id="mode-tile-gsc"') < setup, 'Settings label, role and mode tiles are inside one tile');
ok(/collapsible-toggle collapsible-toggle-plain" onclick="toggleCollapsibleSection\('mb-details'/.test(html), 'Setup checklist & diagnostics has no rule above it');
ok(/\.collapsible-toggle-plain \{[^}]*border-top: none[^}]*margin-top: 0\.[5-9]/.test(html), '... but a small gap');
ok(!/hgroup-divider"><\/div>\n      <\/div>\n\n      <!-- Deliberately OUTSIDE/.test(html), 'no divider line above Settings');
process.exit(failed ? 1 : 0);
