// "Install or Update": checklist left, the terminal right of it and only when it holds something (gui_installer/status_page.html).
//   node test_tools/install_terminal_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- install terminal (begin) ----');
const b = html.indexOf('// ---- install terminal (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { installTerminalWanted };')();
let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }
const el = (text, cls) => ({ textContent: text, classList: { contains: (c) => c === cls } });

ok(!T.installTerminalWanted(el('Terminal output will appear here', 'log-placeholder')), 'the placeholder takes no room');
ok(!T.installTerminalWanted(el('  \n', '')), 'empty: hidden');
ok(T.installTerminalWanted(el('Checking versions', '')), 'output: shown');
ok(T.installTerminalWanted(el('Reset failed', '')), 'a message: shown');
ok(!T.installTerminalWanted(null), 'no element: hidden');

const area = html.indexOf('<div id="install-run-area">');
const list = html.indexOf('<ul id="phase-checklist"');
const box = html.indexOf('<div id="install-terminal" style="display:none;">');
const groups = html.indexOf('<div id="install-groups">');
ok(area > 0 && list > area && box > list && groups > box, 'checklist, then the terminal, both above the settings');
const inside = html.slice(box, groups);
for (const part of ['<span>Terminal</span>', 'id="log-chevron"', 'id="log"', 'id="log-expand-btn"', "copyTerminal('log', this)"]) {
  ok(inside.includes(part), 'the terminal block holds ' + part);
}
ok(html.split('id="log"').length === 2, 'there is one install terminal');
if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all ok');
