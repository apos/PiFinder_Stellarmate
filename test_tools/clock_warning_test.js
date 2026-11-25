// Runs the clock-warning functions of gui_installer/status_page.html (between "Clock warnings (begin)" and "(end)")
// under node, no browser:   node test_tools/clock_warning_test.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'gui_installer', 'status_page.html'), 'utf8');
const a = html.indexOf('// ---- Clock warnings (begin) ----');
const b = html.indexOf('// ---- Clock warnings (end) ----');
if (a < 0 || b < 0) { console.error('markers not found'); process.exit(2); }
const T = new Function(html.slice(a, b) + '\nreturn { clockFormatParts, clockSkewText, clockSkyTimeModel, clockBannerModel };')();

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

eq(T.clockSkewText(10 * 3600 + 24 * 60), '10 h 24 min', 'hours and minutes');
eq(T.clockSkewText(-45 * 60), '45 min', 'minutes only, sign ignored');
eq(T.clockSkewText(3 * 86400), '3 days', 'days');

const base = { pi_time_utc: '2026-11-25T20:58:27+00:00', timezone: 'Europe/Berlin', mount_clock_warn: false, pi_clock_warn: false,
  mount_skew_sec: 100, mount_time_utc: '2026-11-25T20:56:47+00:00' };
eq(T.clockSkyTimeModel(null, ms, 0), null, 'no reading yet: no line');
let m = T.clockSkyTimeModel(base, ms, 0);
ok(m && !m.warn && m.time === '21:58 CET' && m.tail === null, 'all clocks agree: grey line, no tail');
m = T.clockSkyTimeModel(Object.assign({}, base, { mount_clock_warn: true }), ms, 0);
ok(m.warn && m.tail === 'mount clock differs', 'mount clock differs: warn with that tail');
m = T.clockSkyTimeModel(Object.assign({}, base, { pi_clock_warn: true }), ms, 0);
ok(!m.warn && m.tail === 'Pi clock not NTP-synced', 'Pi not NTP-synced: grey note, no warning');
// the line follows the Pi's clock, not the browser's: a browser 2 h behind still shows the Pi time
m = T.clockSkyTimeModel(base, ms - 2 * 3600 * 1000, 2 * 3600 * 1000);
eq(m.time, '21:58 CET', 'browser clock offset is corrected by the server offset');

const mountOff = Object.assign({}, base, { mount_clock_warn: true, mount_skew_sec: 10 * 3600 + 24 * 60, mount_time_utc: '2026-11-25T10:34:27+00:00' });
let bn = T.clockBannerModel(mountOff, {});
ok(bn.mount, 'mount strip');
ok(bn.text.indexOf('10 h 24 min behind') > 0, 'text names the size and direction: ' + bn.text.slice(0, 60));
eq(bn.piClock, '21:58:27 CET', 'Pi clock shown');
eq(bn.mountClock, '11:34:27 CET', 'mount clock shown');
bn = T.clockBannerModel(Object.assign({}, mountOff, { mount_skew_sec: -3700 }), {});
ok(bn.text.indexOf('1 h 2 min ahead of') > 0, 'a mount ahead of the Pi says ahead');
bn = T.clockBannerModel(mountOff, { mount_clock: true });
ok(!bn.mount, 'a dismissed strip stays hidden');
bn = T.clockBannerModel(Object.assign({}, base, { pi_clock_warn: true }), {});
ok(!bn.mount && bn.pi === undefined, 'Pi not NTP-synced: no strip at all');
bn = T.clockBannerModel(base, {});
ok(!bn.mount, 'no strip when everything agrees');
bn = T.clockBannerModel(null, {});
ok(!bn.mount, 'no reading: no strip');

if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('all ok');
