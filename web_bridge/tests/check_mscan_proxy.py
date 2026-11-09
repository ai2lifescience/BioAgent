"""Check DuckDB-compatible proxy normalization without network calls."""
import unittest
from web_bridge.adapters.mscan.run import normalize_proxy_environment


class ProxyTests(unittest.TestCase):
    def test_root_slash_only(self):
        env = {'http_proxy': 'http://127.0.0.1:10801/',
               'HTTPS_PROXY': 'https://user:password@proxy:8443/',
               'NO_PROXY': 'localhost,192.168.0.0/16', 'AGENT_PROXY': 'socks5h://localhost:10801'}
        result = normalize_proxy_environment(env)
        self.assertEqual(result['http_proxy'], 'http://127.0.0.1:10801')
        self.assertEqual(result['HTTPS_PROXY'], 'https://user:password@proxy:8443')
        self.assertEqual(result['NO_PROXY'], env['NO_PROXY'])
        self.assertEqual(result['AGENT_PROXY'], env['AGENT_PROXY'])
        self.assertTrue(env['http_proxy'].endswith('/'))
        self.assertEqual(normalize_proxy_environment(result), result)

    def test_other_values_preserved(self):
        for value in ('', 'http://proxy:80', 'http://proxy/path/', 'socks5://proxy:80/',
                      'http://proxy/?q=1', 'http://proxy/#fragment', 'http://[broken/'):
            with self.subTest(value=value):
                self.assertEqual(normalize_proxy_environment({'http_proxy': value}), {'http_proxy': value})


if __name__ == '__main__':
    unittest.main()
