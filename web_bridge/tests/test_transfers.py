import json
import unittest
from unittest.mock import patch
from auth import principal_scope
from web_bridge.transfer.service import Transfers
from web_bridge.tests.test_integration import WebsiteIntegrationTests as Fixture

class TransferTests(unittest.TestCase):
    setUp=Fixture.setUp
    request=Fixture.request
    login=Fixture.login
    configure=Fixture.configure
    service=Fixture.service

    def prepare(self):
        self.configure()
        return Transfers()

    def test_owner_site_manifest_and_lease_boundaries(self):
        transfers=self.prepare()
        with principal_scope(self.alice),patch('web_bridge.adapters.bioagent.BioAgentHost.list_files',return_value=[{'path':'uploads/one.txt','size':3}]):
            job=transfers.create(self.sid,'fixture','push',{'paths':['uploads/one.txt'],'destination':{'collection':'notes'}})
            with self.assertRaises(ValueError):transfers.create(self.sid,'fixture','push',{'paths':['elsewhere/private']})
        with principal_scope(self.bob):
            with self.assertRaises(Exception):transfers.status(job['transfer_id'])
        self.assertEqual(transfers.pending('other')['commands'],[])
        item=transfers.pending('fixture')['commands'][0]
        with self.assertRaises(Exception):transfers.artifact('fixture',item['id'],'unselected.txt')
        with self.assertRaises(Exception):transfers.artifact('other',item['id'],'uploads/one.txt')
        self.assertEqual(transfers.artifact('fixture',item['id'],'uploads/one.txt')['owner'],self.alice.user_id)
        with self.assertRaises(Exception):transfers.acknowledge('fixture',{'id':item['id'],'lease':'wrong','ok':True})
        transfers.acknowledge('fixture',{**item,'ok':True,'result':{'saved':True}})
        with self.assertRaises(Exception):transfers.artifact('fixture',item['id'],'uploads/one.txt')
        with principal_scope(self.alice):self.assertEqual(transfers.status(item['id'])['state'],'succeeded')

    def test_pull_scopes_do_not_grant_unrelated_session_access(self):
        transfers=self.prepare()
        with principal_scope(self.alice):
            transfers.create(self.sid,'fixture','pull',{'resource_id':'resource'})
        item=transfers.pending('fixture')['commands'][0]
        with principal_scope(self.alice):
            transfers.authorize_upload('fixture',item['id'],self.sid)
            with self.assertRaises(Exception):transfers.authorize_upload('fixture',item['id'],'other-session')
        with principal_scope(self.bob):
            with self.assertRaises(Exception):transfers.authorize_upload('fixture',item['id'],self.sid)
        with transfers.bridge.db(True) as db:db.execute('UPDATE website_commands SET expires=0')
        retry=transfers.pending('fixture')['commands'][0]
        self.assertEqual(retry['id'],item['id'])
        self.assertNotEqual(retry['lease'],item['lease'])
        with self.assertRaises(Exception):transfers.acknowledge('fixture',{**item,'ok':True})

    def test_poll_skips_active_local_work_without_replacing_its_lease(self):
        transfers=self.prepare()
        with principal_scope(self.alice):
            first=transfers.create(self.sid,'fixture','search',{})
            second=transfers.create(self.sid,'fixture','search',{})
        active=transfers.pending('fixture')['commands'][0]
        self.assertEqual(active['id'],first['transfer_id'])
        with transfers.bridge.db(True) as db:
            db.execute('UPDATE website_commands SET expires=0 WHERE id=?',(active['id'],))
        status,_,data=self.service('commands',{'exclude_ids':[active['id']]})
        self.assertEqual(status,200,data)
        self.assertEqual(json.loads(data)['commands'][0]['id'],second['transfer_id'])
        with transfers.bridge.db() as db:
            row=db.execute('SELECT lease,attempts FROM website_commands WHERE id=?',(active['id'],)).fetchone()
        self.assertEqual(row['lease'],active['lease'])
        self.assertEqual(row['attempts'],1)
        resumed=transfers.pending('fixture')['commands'][0]
        self.assertEqual(resumed['id'],active['id'])
        self.assertNotEqual(resumed['lease'],active['lease'])
        for invalid in ['not-a-list',[None],['invalid-id']]:
            with self.assertRaises(ValueError):transfers.pending('fixture',exclude_ids=invalid)

    def test_command_service_protocol(self):
        transfers=self.prepare()
        with principal_scope(self.alice):transfers.create(self.sid,'fixture','search',{'query':'sample'})
        status,_,body=self.service('commands',{})
        self.assertEqual(status,200,body)
        self.assertEqual(len(json.loads(body)['commands']),1)

    def test_command_upload_into_standalone_session(self):
        transfers=self.prepare()
        with principal_scope(self.alice):
            job=transfers.create(self.sid,'fixture','pull',{'resource_id':'sample-file'})
        transfers.pending('fixture')
        body={'command_id':job['transfer_id'],'session_id':self.sid,'resource_id':'sample-file','revision':'one','filename':'test.txt','size':3}
        self.assertNotEqual(self.service('uploads',{k:v for k,v in body.items() if k!='command_id'})[0],200)
        status,_,data=self.service('uploads',body)
        self.assertEqual(status,200,data)
        upload=json.loads(data)['upload_id']
        self.assertEqual(self.service('uploads/'+upload,b'abc',method='PATCH',**{'Upload-Offset':'0'})[0],200)
        status,_,data=self.service('uploads/'+upload+'/complete',{})
        self.assertEqual(status,200,data)
        self.assertIn('path',json.loads(data))
        self.assertNotEqual(self.service('artifact?session_id='+self.sid+'&path=unrelated',method='GET')[0],200)

    def test_heartbeat_failure_retry_and_disabled_account(self):
        from auth import AuthStore, database
        transfers=self.prepare()
        with principal_scope(self.alice):transfers.create(self.sid,'fixture','search',{})
        item=transfers.pending('fixture')['commands'][0]
        self.assertTrue(transfers.heartbeat('fixture',item)['renewed'])
        transfers.acknowledge('fixture',{**item,'ok':False,'result':{'error':'temporary failure'}})
        with principal_scope(self.alice):
            self.assertEqual(transfers.retry(item['id'])['transfer_id'],item['id'])
        with database(AuthStore().path) as db:db.execute('UPDATE users SET disabled=1 WHERE user_id=?',(self.alice.user_id,))
        self.assertEqual(transfers.pending('fixture')['commands'],[])
        with transfers.bridge.db() as db:self.assertEqual(db.execute('SELECT state FROM website_commands WHERE id=?',(item['id'],)).fetchone()['state'],'failed')

    def test_backend_cannot_claim_a_nonexistent_pull_file(self):
        transfers=self.prepare()
        with principal_scope(self.alice):transfers.create(self.sid,'fixture','pull',{'resource_id':'sample'})
        item=transfers.pending('fixture')['commands'][0]
        with patch('web_bridge.adapters.bioagent.BioAgentHost.list_files',return_value=[]):
            with self.assertRaises(ValueError):transfers.acknowledge('fixture',{**item,'ok':True,'result':{'file':{'path':'invented'}}})

    def test_owned_pipeline_bundle_can_be_selected_and_streamed(self):
        import io
        import zipfile
        from urllib.parse import urlencode
        from harness.sandbox import execution_access
        from tools.infrastructure.pipeline_engine import broker
        from tools.infrastructure.pipeline_engine.store import JobStore
        transfers=self.prepare()
        with principal_scope(self.alice):
            access=execution_access()
            store=JobStore(broker._owned(access.workspace(self.sid),access))
            job=store.create({'pipeline_name':'fixture'})
            path='pipeline-bundles/'+job['job_id']+'/results.zip'
            with self.assertRaises(ValueError):transfers.create(self.sid,'fixture','push',{'paths':[path]})
            store.update(job['job_id'],status='succeeded',result={'output_records':[]})
            command=transfers.create(self.sid,'fixture','push',{'paths':[self.file['path'],path]})
            with self.assertRaises(ValueError):transfers.create(self.sid,'fixture','push',{'paths':['pipeline-bundles/../results.zip']})
        from web_bridge.identity import Federation
        Federation().link('fixture','external-bob','bob')
        with principal_scope(self.bob):
            with self.assertRaises(ValueError):transfers.create(self.bob_sid,'fixture','push',{'paths':[path]})
        item=transfers.pending('fixture')['commands'][0]
        bundle=item['payload']['files'][1]
        self.assertTrue(bundle['virtual'])
        self.assertNotIn('size',bundle)  # A generated ZIP has no guessed content length.
        status,_,data=self.service('command-artifact?'+urlencode({'id':command['transfer_id'],'path':path}),method='GET')
        self.assertEqual(status,200,data)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
        self.assertNotEqual(self.service('command-artifact?'+urlencode({'id':command['transfer_id'],'path':path}),site='other',method='GET')[0],200)

    def test_bundle_push_exposes_members_once_for_native_import(self):
        import io
        from contextlib import contextmanager
        from urllib.parse import urlencode
        from harness.sandbox import execution_access
        from tools.infrastructure.pipeline_engine import broker
        from tools.infrastructure.pipeline_engine.store import JobStore
        transfers=self.prepare()
        content=b'InputReads\tReadsAfterQC\tReadsAfterHostRemoval\n10\t9\t8\n'
        with principal_scope(self.alice):
            access=execution_access()
            store=JobStore(broker._owned(access.workspace(self.sid),access))
            job=store.create({})
            store.update(job['job_id'],status='succeeded',result={'output_records':[
                {'remote':True,'name':'qc_counts.tsv','wdl_output':'MetagenomicQc.qc_counts','size':len(content)},
                {'remote':True,'name':'clean.R1.fq','size':4}]})
            bundle='pipeline-bundles/'+job['job_id']+'/results.zip'
            member='pipeline-artifacts/'+job['job_id']+'/0/qc_counts.tsv'
            command=transfers.create(self.sid,'fixture','push',{'paths':[self.file['path'],bundle]})
        item=transfers.pending('fixture')['commands'][0]
        files=item['payload']['files']
        self.assertEqual(len(files),4)
        self.assertEqual({f['name'] for f in files if f.get('kind')=='pipeline_output'}, {'qc_counts.tsv','clean.R1.fq'})
        summary=next(f for f in files if f['name']=='qc_counts.tsv')['pipeline_result']
        self.assertEqual(summary['output_key'],'MetagenomicQc.qc_counts')
        self.assertEqual(summary['job_id'],job['job_id'])
        self.assertNotIn('remote',summary)
        @contextmanager
        def stream(*args,**kwargs):
            yield {'Body':io.BytesIO(content),'ContentLength':len(content)},{}
        with patch.object(broker,'remote_stream',stream):
            status,_,data=self.service('command-artifact?'+urlencode({'id':command['transfer_id'],'path':member}),method='GET')
        self.assertEqual(status,200,data)
        self.assertEqual(data,content)
        transfers.acknowledge('fixture',{**item,'ok':True})
        with principal_scope(self.alice):
            transfers.create(self.sid,'fixture','push',{'paths':[member,bundle,self.file['path'],member]})
        repeated=transfers.pending('fixture')['commands'][0]['payload']['files']
        self.assertEqual(len(repeated),4)
        self.assertEqual(len({f['path'] for f in repeated}),4)
        with principal_scope(self.alice):
            store.update(job['job_id'],artifact_status='unavailable')
            with self.assertRaisesRegex(ValueError,'not available'):
                transfers.create(self.sid,'fixture','push',{'paths':[bundle]})

    def test_local_bundle_members_are_published_through_session_boundary(self):
        import hashlib
        from harness.sandbox import execution_access
        from tools.infrastructure.pipeline_engine import broker
        from tools.infrastructure.pipeline_engine.store import JobStore
        transfers=self.prepare()
        with principal_scope(self.alice):
            access=execution_access()
            root=access.workspace(self.sid)
            private=broker._owned(root,access)
            store=JobStore(private)
            job=store.create({'pipeline_name':'fixture'})
            source=store.directory(job['job_id'])/'qc_counts.tsv'
            data=b'InputReads\tReadsAfterQC\tReadsAfterHostRemoval\n10\t9\t8\n'
            source.write_bytes(data)
            store.update(job['job_id'],status='succeeded',result={'output_records':[{
                'name':source.name,'wdl_output':'MetagenomicQc.qc_counts','workspace_path':source.relative_to(private).as_posix(),
                'exists':True,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()},
                {'name':'optional_report','exists':False,'required':False,'size':0}]})
            bundle='pipeline-bundles/'+job['job_id']+'/results.zip'
            transfers.create(self.sid,'fixture','push',{'paths':[bundle]})
            files=transfers.pending('fixture')['commands'][0]['payload']['files']
            member=files[1]
            self.assertEqual(member['kind'],'pipeline_output')
            self.assertEqual(member['pipeline_result']['output_key'],'MetagenomicQc.qc_counts')
            self.assertTrue(member['path'].startswith('outputs/pipelines/'+job['job_id']+'/'))
            self.assertEqual((root/member['path']).read_bytes(),data)
            from web_bridge.ports import get_host
            selected=get_host().resolve_transfer_files(self.sid,[member['path']])
            self.assertEqual(selected[0]['pipeline_result']['output_key'],'MetagenomicQc.qc_counts')
            (root/member['path']).write_bytes(b'modified public copy')
            with self.assertRaisesRegex(ValueError,'changed'):
                get_host().resolve_transfer_files(self.sid,[member['path']])
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                transfers.create(self.sid,'fixture','push',{'paths':[bundle]})
