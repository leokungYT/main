import os
import sys

sys.path.insert(0, 'api')
from lgr_api import LGRClient

c = LGRClient('u1', 'lf', proxy_pool=['http://proxy1:8080', 'socks5://proxy2:1080'])
print('proxy_count=', len(c.proxy_pool))
print('first_proxy=', c.proxy_pool[0])

os.environ['LGR_PROXY_POOL'] = 'http://env1:8080, http://env2:8080'
d = LGRClient('u2', 'lf2')
print('env_proxy_count=', len(d.proxy_pool))
print('env_first=', d.proxy_pool[0])
