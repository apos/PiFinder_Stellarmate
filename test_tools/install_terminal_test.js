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
// The "is running" banner's button.
const c = html.indexOf('// ---- show install run (begin) ----');
const d = html.indexOf('// ---- show install run (end) ----');
ok(c > 0 && d > c, 'the show function is there');
const banner = html.slice(html.indexOf('<div id="cc-update-running-banner"'), html.indexOf('<div id="last-run-banner"'));
ok(banner.includes('onclick="showInstallRun()"') && banner.includes('Show Install or Update'), 'the running banner has the button');
function page(tile, log, tileTop, scrolled) {
  const els = { 'install-tile-body': { style: { display: tile } }, 'log-wrap': { style: { display: log } }, 'cc-header-sticky': { offsetHeight: 100 },
    'install-tile': { getBoundingClientRect: () => ({ top: tileTop }) } };
  const did = [];
  const run = new Function('document', 'window', 'toggleTileBody', 'toggleCollapsibleSection', html.slice(c, d) + '\nshowInstallRun();');
  run({ getElementById: (id) => els[id] }, { scrollY: scrolled, scrollTo: (o) => did.push('scroll ' + o.top) },
    (id) => did.push('open ' + id), (id) => did.push('open ' + id));
  return did.join(', ');
}
ok(page('', '', 700, 50) === 'scroll 642', 'open tile: only scrolls, just below the header');
ok(page('none', 'none', 700, 0) === 'open install-tile-body, open log-wrap, scroll 592', 'folded away: opens the tile and the terminal first');
ok(page('', '', 20, 0) === 'scroll 0', 'never scrolls above the top');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all ok');
