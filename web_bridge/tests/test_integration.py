"""Real HTTP checks for generic website federation, persistence and streamed files."""
import json
import hashlib
import os
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from auth import principal_scope
from web_bridge.identity import Federation
from web_bridge.bridge import issue_ticket
from web_bridge.conversations import WebsiteAccounts
from evals import test_user_isolation as isolation_tests


class WebsiteIntegrationTests(unittest.TestCase):
    setUp = isolation_tests.UserIsolationTests.setUp
    request = isolation_tests.UserIsolationTests.request
    login = isolation_tests.UserIsolationTests.login

    def configure(self):
        self.config = patch.dict(os.environ, {'AGENT_WEBSITE_CLIENTS': json.dumps({
            'fixture': {'secret': 'c'*40, 'origins': ['https://fixture.test']},
            'other': {'secret': 'd'*40, 'origins': ['https://other.test']},
        })})
        self.config.start(); self.addCleanup(self.config.stop)
        Federation().link('fixture', 'external-alice', 'alice')
        Federation().link('other', 'external-alice', 'alice')

    def test_explicit_empty_origin_allowlist_disables_clients(self):
        self.configure()
        with patch.dict(os.environ, {'AGENT_WEBSITE_SITES': '{}'}):
            self.assertEqual(self.service('bootstrap', {'origin':'https://fixture.test'})[0],400)

    def test_expired_grants_and_disabled_users_cannot_sign_in(self):
        from auth import AuthStore, database
        self.configure()
        grant = self.bootstrap()
        with database(AuthStore().path) as db:
            db.execute('UPDATE website_grants SET expires=0')
        self.assertEqual(self.request('/auth/website/exchange', method='POST', body=grant)[0], 401)
        grant = self.bootstrap()
        with database(AuthStore().path) as db:
            db.execute('UPDATE users SET disabled=1 WHERE user_id=?', (self.alice.user_id,))
        self.assertEqual(self.request('/auth/website/exchange', method='POST', body=grant)[0], 401)
        self.assertEqual(self.service('bootstrap', {'origin':'https://fixture.test'})[0], 401)

    def service(self, operation, body=None, *, site='fixture', subject='external-alice', method='POST', **extra):
        headers = {'X-Website-Site': site, 'X-Website-Subject': subject,
                   'Authorization': 'Bearer ' + ('c'*40 if site=='fixture' else 'd'*40), **extra}
        if method=='POST': body={'subject': subject, **(body or {})}
        return self.request('/website/service/'+operation, method=method, body=body, headers=headers)

    def bootstrap(self, subject='external-alice'):
        status, _, body=self.service('bootstrap', {'origin':'https://fixture.test'}, subject=subject)
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def exchange(self, grant):
        status, headers, body=self.request('/auth/website/exchange',method='POST',body=grant)
        self.assertEqual(status,200,body)
        return json.loads(body), headers['Set-Cookie'].split(';')[0]

    def test_login_grant_identity_origin_replay_and_stable_conversation(self):
        self.configure()
        grant=self.bootstrap()
        self.assertEqual(self.request('/auth/website/exchange',method='POST',body={**grant,'origin':'https://other.test'})[0],400)
        value,cookie=self.exchange(grant)
        self.assertEqual(value['user']['id'],self.alice.user_id)
        self.assertEqual(self.request('/auth/website/exchange',method='POST',body=grant)[0],401)
        again,_=self.exchange(self.bootstrap())
        self.assertEqual(value['session_id'],again['session_id'])
        other,_=self.exchange(self.bootstrap('external-bob'))
        self.assertNotEqual(other['user']['id'],value['user']['id'])
        self.assertEqual(self.request('/sessions/'+other['session_id']+'/messages',cookie=cookie)[0],404)
        self.assertEqual(self.request('/website/service/results',method='POST',body={'subject':'external-alice'})[0],401)
        self.assertEqual(self.service('results', Origin='https://fixture.test')[0],401)

    def test_shared_sso_user_id_needs_no_manual_account_link(self):
        clients = {
            'fixture': {'secret': 'c'*40, 'origins': ['https://fixture.test'], 'identity_mode': 'shared_user_id'},
            'other': {'secret': 'd'*40, 'origins': ['https://other.test'], 'identity_mode': 'shared_user_id'},
        }
        identity = {'user_id': 'oos-user-42', 'username': 'oos.alice'}
        with patch.dict(os.environ, {'AGENT_WEBSITE_CLIENTS': json.dumps(clients)}):
            status, _, raw = self.service('bootstrap', {'origin': 'https://fixture.test', 'identity': identity},
                                          subject=identity['user_id'])
            self.assertEqual(status, 200, raw)
            value, _ = self.exchange(json.loads(raw))
            self.assertEqual(value['user'], {'id': identity['user_id'], 'name': identity['username']})
            self.assertLessEqual(value['expires_in'], 300)

            status, _, raw = self.service('bootstrap', {'origin': 'https://other.test', 'identity': identity},
                                          site='other', subject=identity['user_id'])
            self.assertEqual(status, 200, raw)
            other, _ = self.exchange(json.loads(raw))
            self.assertEqual(other['user']['id'], identity['user_id'])

            mismatched = {'user_id': 'another-user', 'username': 'oos.alice'}
            self.assertEqual(self.service('bootstrap', {'origin': 'https://fixture.test', 'identity': mismatched},
                                          subject='oos-user-43')[0], 400)
            self.assertEqual(self.service('bootstrap', {'origin': 'https://fixture.test'},
                                          subject='new-shared-user')[0], 400)

    def test_streamed_import_download_ownership_and_persistent_results(self):
        self.configure(); value,cookie=self.exchange(self.bootstrap()); sid=value['session_id']
        status,_,body=self.service('uploads',{'session_id':sid,'resource_id':'sample:read1','revision':'v1','filename':'reads.bin','size':1024*1024+3})
        self.assertEqual(status,200,body); identifier=json.loads(body)['upload_id']
        first=b'a'*(1024*1024)
        self.assertEqual(self.service('uploads/'+identifier,first,method='PATCH',**{'Upload-Offset':'0'})[0],200)
        resumed=json.loads(self.service('uploads',{'session_id':sid,'resource_id':'sample:read1','revision':'v1','filename':'reads.bin','size':len(first)+3})[2])
        self.assertEqual((resumed['upload_id'],resumed['offset']),(identifier,len(first)))
        self.assertEqual(self.service('uploads/'+identifier,b'xyz',method='PATCH',subject='external-bob',**{'Upload-Offset':str(len(first))})[0],404)
        self.assertEqual(self.service('uploads/'+identifier,b'xyz',method='PATCH',**{'Upload-Offset':str(len(first))})[0],200)
        self.assertEqual(self.service('uploads/'+identifier+'/complete',{'sha256':'0'*64})[0],400)
        checksum=hashlib.sha256(first+b'xyz').hexdigest()
        status,_,body=self.service('uploads/'+identifier+'/complete',{'sha256':checksum});self.assertEqual(status,200,body)
        file=json.loads(body); query=urlencode({'session_id':sid,'path':file['path']})
        self.assertEqual(file['sha256'],checksum)
        repeated=json.loads(self.service('uploads',{'session_id':sid,'resource_id':'sample:read1','revision':'v1','filename':'reads.bin','size':len(first)+3})[2])
        self.assertEqual(repeated['file']['path'],file['path'])
        status,headers,data=self.service('artifact?'+query,method='GET',Range='bytes=1048576-1048578')
        self.assertEqual((status,data),(206,b'xyz'))
        self.assertEqual(self.service('artifact?'+query,method='GET',subject='external-bob')[0],404)
        self.assertEqual(self.service('artifact?'+query,method='GET',site='other')[0],404)
        self.assertEqual(self.request('/workspace/file?'+query)[0],401)
        status,_,body=self.service('results');self.assertEqual(status,200,body)
        self.assertTrue(json.loads(body)['conversations'][0]['files'])
        with principal_scope(self.alice):
            accounts=WebsiteAccounts(); new=accounts.conversation('fixture',new=True)
        latest,_=self.exchange(self.bootstrap());self.assertEqual(latest['session_id'],new)
        self.assertEqual(len(json.loads(self.service('results')[2])['conversations']),2)

    def test_reload_reattaches_pending_binding_without_breaking_worker_token(self):
        self.configure(); value,_=self.exchange(self.bootstrap());sid=value['session_id']
        with principal_scope(self.alice):
            kwargs={'site_id':'fixture','origin':'https://fixture.test','instance_id':'first','session_id':sid,'context':{'revision':'one'},'capabilities':['readTable']}
            ticket=lambda:issue_ticket('x'*40,site_id='fixture',origin='https://fixture.test',subject=self.alice.user_id)
            first=self.bridge.connect(ticket=ticket(),**kwargs)
            with self.store.locked_session(sid) as (session,_):session.metadata['website_binding']=first
            second=self.bridge.connect(ticket=ticket(),**{**kwargs,'instance_id':'second'})
            self.assertEqual(first['binding_id'],second['binding_id'])
            self.assertEqual(first['token'],second['token'])

    def test_cookie_free_exchange_single_use_download_and_scoped_logout(self):
        self.configure()
        grant=self.bootstrap()
        status,headers,raw=self.request('/auth/website/exchange',method='POST',body={**grant,'credential_mode':'bearer'})
        self.assertEqual(status,200,raw);self.assertNotIn('Set-Cookie',headers)
        value=json.loads(raw);bearer={'Authorization':'Bearer '+value['access_token']}
        self.assertEqual(self.request('/sessions',headers=bearer)[0],200)
        from interfaces.api import write_workspace_file
        with principal_scope(self.alice):file=write_workspace_file(value['session_id'],'result.txt',b'example report')
        payload={'site_id':'fixture','session_id':value['session_id'],'path':file['path']}
        status,_,raw=self.request('/website/artifact-ticket',method='POST',body=payload,headers=bearer)
        self.assertEqual(status,200,raw);token=json.loads(raw)['token']
        status,headers,data=self.request('/website/download/'+token)
        self.assertEqual((status,data),(200,b'example report'));self.assertIn('attachment',headers['Content-Disposition'])
        self.assertEqual(self.request('/website/download/'+token)[0],401)
        self.assertEqual(self.request('/website/artifact-ticket',method='POST',body=payload,cookie=self.bob_cookie)[0],404)
        self.assertEqual(self.service('revoke')[0],200)
        self.assertEqual(self.request('/sessions',headers=bearer)[0],401)
        self.assertEqual(self.request('/sessions',cookie=self.alice_cookie)[0],200)


if __name__=='__main__': unittest.main()
