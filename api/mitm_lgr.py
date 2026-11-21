"""mitmproxy addon — log every LGR request to /tmp/mitm_lgr.log."""
import json, os, time
from mitmproxy import http

LOG = os.environ.get('LGR_MITM_LOG', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mitm_lgr.log'))
HOSTS = ('rangers-api.line-apps.com', 'game-api.line.me', 'lg-config.line-apps.com',
         'lan3rd.line.me', 'access.line.me')


def _safe(b):
    if not b: return ''
    try: return b.decode('utf-8','replace')
    except: return '<binary ' + str(len(b)) + 'b>'


def response(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not any(h in host for h in HOSTS): return
    rec = {
        't': time.time(),
        'host': host,
        'method': flow.request.method,
        'url': flow.request.pretty_url,
        'req_headers': dict(flow.request.headers),
        'req_body_hex': flow.request.raw_content.hex()[:1000] if flow.request.raw_content else '',
        'req_body': _safe(flow.request.raw_content)[:1500],
        'status': flow.response.status_code if flow.response else None,
        'resp_headers': dict(flow.response.headers) if flow.response else {},
        'resp_body': _safe(flow.response.raw_content)[:1500] if flow.response else '',
    }
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'[{flow.request.method}] {flow.request.pretty_url} -> {rec["status"]}')
