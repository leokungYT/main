import sys
sys.path.insert(0, '.')

from lgr_api import extract_proxy_candidates, LGRClient

HTML = '''
<div>14.1.1.1:8080</div>
<span>203.0.113.55:3128</span>
<a href="http://198.51.100.2:8000">proxy</a>
'''

proxies = extract_proxy_candidates(HTML)
assert 'http://14.1.1.1:8080' in proxies
assert 'http://203.0.113.55:3128' in proxies
assert 'http://198.51.100.2:8000' in proxies

client = LGRClient('u1', 'lf', proxy_pool=None, use_free_proxy_fallback=False)
assert isinstance(client.proxy_pool, list)
print('OK')
