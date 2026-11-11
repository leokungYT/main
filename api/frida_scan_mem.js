// api/frida_scan_mem.js  v3
// เจอ Content-Length header ใน heap @ 0x5b76a3d9 แล้ว → dump 4KB รอบ hit
// ส่ง raw bytes กลับทาง send(..., buffer) ให้ python save เป็น .bin

send('[+] mem scanner v3 — dump mode');

function hexAscii(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) {
        var c = bytes[i];
        if (c >= 32 && c < 127) s += String.fromCharCode(c);
        else s += '.';
    }
    return s;
}

function hexOf(s) {
    var h = '';
    for (var i = 0; i < s.length; i++) {
        var v = s.charCodeAt(i).toString(16);
        h += (v.length < 2 ? '0' + v : v) + ' ';
    }
    return h.trim();
}

function dumpHit(addr, before, after, tag) {
    var start = ptr(addr).sub(before);
    var len = before + after;
    try {
        var buf = Memory.readByteArray(start, len);
        send({ tag: tag, addr: addr.toString(), len: len }, buf);
        send('[' + tag + '] dumped ' + len + ' bytes from @' + start);
    } catch (e) { send('[dump err] ' + e); }
}

function scanAndDump(needle, prot, label, before, after, maxHits) {
    before = before || 128;
    after = after || 4096;
    maxHits = maxHits || 20;
    var hits = 0;
    var ranges = Process.enumerateRanges({ protection: prot, coalesce: true });
    send('[scan ' + prot + '] ' + label + ' ranges=' + ranges.length);
    ranges.forEach(function (r) {
        try {
            var matches = Memory.scanSync(r.base, r.size, hexOf(needle));
            matches.forEach(function (m) {
                hits++;
                if (hits > maxHits) return;
                dumpHit(m.address, before, after, label + '_' + hits);
            });
        } catch (e) {}
    });
    send('[scan ' + prot + '] ' + label + ' total=' + hits);
}

setTimeout(function () {
    send('[+] v3 start — dumping HTTP request blobs');

    // 1) HTTP request headers — Content-Length means full request assembled
    scanAndDump('Content-Length:', 'rw-', 'req_contlen', 256, 4096, 10);

    // 2) HTTP/1.1 response/request line
    scanAndDump('HTTP/1.1', 'rw-', 'http11', 256, 2048, 10);

    // 3) msgpack json alternative
    scanAndDump('application/x-msgpack', 'rw-', 'ct_msgpack', 384, 2048, 10);
    scanAndDump('application/json', 'rw-', 'ct_json', 384, 2048, 10);

    // 4) known crypto blob location
    scanAndDump('DpRtDpSuINrW', 'rw-', 'enc_blob_runtime', 128, 1024, 5);

    // 5) look for 32-char hex (udid-like) — a..f 0..9 32 times
    //    skip, too broad; instead scan for "udid" minus value
    scanAndDump(' udid', 'rw-', 'space_udid', 64, 384, 20);
    scanAndDump('udid:', 'rw-', 'udid_colon', 64, 384, 20);
    scanAndDump('x-lf-', 'rw-', 'xlf_hdr', 64, 512, 20);
    scanAndDump('X-Lf-', 'rw-', 'XLF_hdr', 64, 512, 20);

    // 6) look for base64 PREFIX of our known blob (4 chars enough)
    scanAndDump('DpRt', 'rw-', 'enc_b64_short', 128, 512, 10);

    // 7) typical cookie set-string
    scanAndDump('udid=', 'rw-', 'cookie_udid', 0, 384, 10);
    scanAndDump('udid=', 'r--', 'cookie_udid_ro', 0, 384, 10);

    send('[+] v3 scans done');
}, 2000);
