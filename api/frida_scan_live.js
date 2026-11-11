// api/frida_scan_live.js  v4 LIVE
// scan ซ้ำทุก 1 วิ นาน 120 วิ — ระหว่างนี้ user click Shop/Gacha/Mission ใน MuMu
// จับ /login, /home, /gift, /ruby, /pass endpoint — dump ทันทีที่เจอ

send('[+] live scanner v4 — scan every 1s for 120s');

function hexOf(s) {
    var h = '';
    for (var i = 0; i < s.length; i++) {
        var v = s.charCodeAt(i).toString(16);
        h += (v.length < 2 ? '0' + v : v) + ' ';
    }
    return h.trim();
}

var _seen = {};
function dumpHit(addr, before, after, tag) {
    var key = tag + '@' + addr;
    if (_seen[key]) return false;
    _seen[key] = true;
    var start = ptr(addr).sub(before);
    try {
        var buf = Memory.readByteArray(start, before + after);
        send({ tag: tag, addr: addr.toString(), len: before + after }, buf);
        return true;
    } catch (e) { return false; }
}

function scanOnce(needle, prot, label, before, after) {
    before = before || 256;
    after = after || 4096;
    var ranges = Process.enumerateRanges({ protection: prot, coalesce: true });
    var hits = 0, newHits = 0;
    ranges.forEach(function (r) {
        try {
            var matches = Memory.scanSync(r.base, r.size, hexOf(needle));
            matches.forEach(function (m) {
                hits++;
                if (dumpHit(m.address, before, after, label)) newHits++;
            });
        } catch (e) {}
    });
    if (newHits > 0) send('[live] ' + label + ' NEW=' + newHits + ' total=' + hits);
}

// targets: LGR-specific endpoints
var TARGETS = [
    { needle: 'POST /login',    label: 'POST_login',   before: 128, after: 3072 },
    { needle: 'POST /home',     label: 'POST_home',    before: 128, after: 2048 },
    { needle: 'POST /gift',     label: 'POST_gift',    before: 128, after: 2048 },
    { needle: 'GET /home',      label: 'GET_home',     before: 128, after: 2048 },
    { needle: '/login/platform', label: 'login_plat',  before: 256, after: 2048 },
    { needle: '/signup/guest',  label: 'signup_guest', before: 256, after: 2048 },
    { needle: 'Host: rangers',  label: 'host_rangers', before: 256, after: 4096 },
    { needle: 'LF_AC=',         label: 'LFAC_runtime', before: 64,  after: 256 },
    { needle: 'udid=',          label: 'udid_runtime', before: 0,   after: 256 },
    { needle: 'guestCookie',    label: 'guest_runtime', before: 64, after: 512 },
    { needle: 'X-Linegame-Timestamp', label: 'xlg_ts', before: 256, after: 2048 },
];

var tickCount = 0;
var maxTicks = 240; // 240 * 0.5 = 120s
send('[+] START click Shop/Gacha/Mission/Collect ใน MuMu ตอนนี้!');

var tickId = setInterval(function () {
    tickCount++;
    TARGETS.forEach(function (t) {
        scanOnce(t.needle, 'rw-', t.label, t.before, t.after);
    });
    if (tickCount % 10 === 0) send('[tick ' + tickCount + '/' + maxTicks + '] still scanning...');
    if (tickCount >= maxTicks) {
        clearInterval(tickId);
        send('[+] live scan done after ' + tickCount + ' ticks');
    }
}, 500);
