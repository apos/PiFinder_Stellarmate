// Runs the clock-and-location functions of gui_installer/status_page.html (between "Clock warnings (begin)" and "(end)")
// under node, no browser:   node test_tools/clock_warning_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- Clock warnings (begin) ----');
const b = html.indexOf('// ---- Clock warnings (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) +
  '\nreturn { clockFormatParts, clockSkyTimeModel, clockOffsetText, clockPlaceText, clockNoticeUpdate, clockNoticeDismiss, clockNoticeModel };')();

let failed = 0;
function ok(cond, msg) { if (!cond) { failed++; console.error('FAIL: ' + msg); } else console.log('ok:   ' + msg); }
const eq = (x, y, msg) => ok(x === y, msg + ' (got ' + JSON.stringify(x) + ')');

// 2026-11-25 20:58:27 UTC is 21:58:27 in Europe/Berlin (CET)
const ms = Date.UTC(2026, 10, 25, 20, 58, 27);
const p = T.clockFormatParts(ms, 'Europe/Berlin');
eq(p.time, '21:58 CET', 'time in the Pi timezone with its abbreviation');
eq(p.clock, '21:58:27 CET', 'clock with seconds');
eq(p.day, '25 Nov', 'day and month');
ok(T.clockFormatParts(ms, 'Not/AZone').time.length > 0, 'an unknown timezone name falls back to the browser zone');

eq(T.clockOffsetText(1), 'UTC+1:00', 'offset east');
eq(T.clockOffsetText(-3.5), 'UTC-3:30', 'offset west with half an hour');
eq(T.clockOffsetText(null), '-', 'no offset');
eq(T.clockPlaceText([49.4776, 8.4508]), '49.478° N, 8.451° E', 'a place');
eq(T.clockPlaceText([-33.9, -70.5]), '33.900° S, 70.500° W', 'south west');
eq(T.clockPlaceText(null), '-', 'no place');

const agree = { pi_time_utc: '2026-11-25T20:58:27+00:00', timezone: 'Europe/Berlin', mismatch: false, mount_warn: false,
  pi_clock_warn: false, current: [], can_set_mount: true, rows: [
    { source: 'KStars (reference)', time_utc: '2026-11-25T20:58:27+00:00', offset: 1, location: [49.4776, 8.4508], note: '', wrong: [] },
    { source: 'Mount (LX200 OnStep)', time_utc: null, offset: null, location: null, note: 'no time reported', wrong: [] }] };
const differ = Object.assign({}, agree, { mismatch: true, mount_warn: true,
  current: ["The mount's location (INDI) is 16 km from KStars' location."] });
const pending = Object.assign({}, differ, { mismatch: false });   // wrong, but not yet long enough

eq(T.clockSkyTimeModel(null, ms, 0), null, 'no reading yet: no line');
let m = T.clockSkyTimeModel(agree, ms, 0);
ok(m && !m.warn && m.time === '21:58 CET' && m.tail === null, 'all agree: grey line, no tail');
m = T.clockSkyTimeModel(differ, ms, 0);
ok(m.warn && m.tail === 'mount time or location differs', 'mount differs: warn with that tail');
m = T.clockSkyTimeModel(Object.assign({}, agree, { pi_clock_warn: true }), ms, 0);
ok(!m.warn && m.tail === 'Pi clock not NTP-synced', 'Pi not NTP-synced: grey note, no warning');
m = T.clockSkyTimeModel(agree, ms - 2 * 3600 * 1000, 2 * 3600 * 1000);
eq(m.time, '21:58 CET', 'browser clock offset is corrected by the server offset');

const ui = { open: false, dismissed: false };
T.clockNoticeUpdate(ui, agree);
ok(!T.clockNoticeModel(agree, ui).show, 'no notice while everything agrees');
T.clockNoticeUpdate(ui, pending);
ok(!ui.open, 'a difference that has not lasted opens nothing');
T.clockNoticeUpdate(ui, differ);
let n = T.clockNoticeModel(differ, ui);
ok(n.show && n.problems.length === 1 && n.canFix && /do not match/.test(n.head), 'the notice opens with the problem and the fix');
eq(n.rows[0].time, '25 Nov, 21:58:27 CET', 'row time in the Pi timezone');
eq(n.rows[1].time, '-', 'a row without time');
ok(/mount may point wrongly/.test(T.clockNoticeModel(Object.assign({}, differ, { rows: [{ source: 'Mount (M)', wrong: ['location'] }] }), ui).head),
  'a wrong mount line: the head says the mount may point wrongly');
ok(!/mount may point/.test(T.clockNoticeModel(Object.assign({}, differ, { rows: [{ source: "PiFinder's computer (x)", wrong: ['time'] }] }), ui).head),
  'only the other computer differs: nothing is claimed about the mount');
T.clockNoticeUpdate(ui, agree);
n = T.clockNoticeModel(agree, ui);
ok(n.show && /agree now/.test(n.head) && n.problems.length === 0, 'it stays open when everything agrees, and says so');
T.clockNoticeDismiss(ui, agree);
ok(!T.clockNoticeModel(agree, ui).show, 'only Dismiss closes it');
T.clockNoticeUpdate(ui, differ);
ok(ui.open, 'a new difference after that opens it again');
T.clockNoticeDismiss(ui, differ);
T.clockNoticeUpdate(ui, differ);
ok(!ui.open, 'dismissed with the difference still there: stays closed');
T.clockNoticeUpdate(ui, agree);
T.clockNoticeUpdate(ui, differ);
ok(ui.open, 'gone and back again: a new notice');
ok(!T.clockNoticeModel(null, { open: true }).head, 'no reading: no content');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all ok');
