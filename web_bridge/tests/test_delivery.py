"""Transport, ownership and retry behavior for durable result handoff."""
import json
import unittest
from unittest.mock import patch
from auth import principal_scope
from web_bridge.delivery import Deliveries
from web_bridge.tests.test_integration import WebsiteIntegrationTests as Fixture

class DeliveryTests(unittest.TestCase):
    setUp=Fixture.setUp
    request=Fixture.request
    login=Fixture.login
    configure=Fixture.configure
    service=Fixture.service

    def prepare(self):
        self.configure()
        with principal_scope(self.alice):
            self.queue.update(self.job['run_id'],'succeeded',result={'answer':'done','evidence':{'files':['pipeline-artifacts/job/0/metrics.json']}})
            return Deliveries()

    def test_signed_in_browser_can_list_sites_without_nested_auth_lock(self):
        self.prepare()
        status,_,body=self.request('/website/sites',method='POST',cookie=self.alice_cookie,body={})
        self.assertEqual(status,200,body)
        self.assertIn('fixture',{r['site_id'] for r in json.loads(body)['sites']})

    def test_destination_contract_is_website_defined(self):
        d=self.prepare()
        with principal_scope(self.alice):
            d.schedule('fixture',self.job['run_id'],{'document_id':'report-42','collection':'lab-notes'})
            self.assertEqual(d.status(self.job['run_id'])['deliveries'][0]['target'],{'document_id':'report-42','collection':'lab-notes'})
            with self.assertRaises(ValueError):d.schedule('fixture',self.job['run_id'],{})

    def test_run_pins_host_destination_and_does_not_publish_empty_answers(self):
        from web_bridge.conversations import WebsiteAccounts
        d=self.prepare()
        target={'sample_id':'sample-a','data_type':'meta'}
        row={'site_id':'fixture','context':json.dumps({'delivery_target':target})}
        with principal_scope(self.alice),patch.object(self.bridge,'_binding',return_value=row):
            WebsiteAccounts().record_run(self.job['run_id'],self.sid,{'binding_id':'binding','token':'token'})
            row['context']=json.dumps({'delivery_target':{'sample_id':'sample-b'}})
            self.assertEqual(d.status(self.job['run_id'])['deliveries'][0]['target'],target)
        with patch('web_bridge.adapters.bioagent.BioAgentHost.list_files',return_value=[]):
            self.assertEqual(d.pending('fixture')['deliveries'],[])
        with principal_scope(self.alice):
            self.assertEqual(d.status(self.job['run_id'])['deliveries'][0]['state'],'not_delivered')

    def test_running_jobs_do_not_starve_later_completed_deliveries(self):
        d=self.prepare()
        with d.bridge.db(True) as db:
            for i in range(25):
                db.execute("INSERT INTO website_deliveries (id,site_id,subject,owner,run_id,session_id,target,baseline,state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(str(i),'fixture','external-alice',self.alice.user_id,str(i),self.sid,'{"document_id":"report"}','null','waiting',f'{i:03d}'))
        file={'path':'outputs/report.md','size':4}
        def job(run):return {'status':'succeeded' if run=='24' else 'running','session_id':self.sid,'result':{'evidence':{'files':[file['path']]}}}
        with patch('web_bridge.adapters.bioagent.BioAgentHost.get_run',side_effect=job),patch('web_bridge.adapters.bioagent.BioAgentHost.list_files',return_value=[file]):
            ready=d.pending('fixture')['deliveries']
        self.assertEqual([r['run_id'] for r in ready],['24'])

    def test_site_owner_share_replay_and_destination_pin(self):
        d=self.prepare()
        target={'sample_id':'sample-a','data_type':'meta'}
        with principal_scope(self.alice):
            code=d.share('fixture',self.job['run_id'])['code']
        with principal_scope(self.bob):
            with self.assertRaises(ValueError):d.redeem('fixture',code,target)
        with principal_scope(self.alice):
            with self.assertRaises(ValueError):d.redeem('other',code,target)
            first=d.redeem('fixture',code,target)
            with self.assertRaises(ValueError):d.redeem('fixture',code,target)
            self.assertEqual(first['id'],d.schedule('fixture',self.job['run_id'],target)['id'])
            self.assertNotEqual(first['id'],d.schedule('fixture',self.job['run_id'],{**target,'sample_id':'sample-b'})['id'])
        self.assertEqual(self.request('/website/delivery-status',method='POST',cookie=self.bob_cookie,body={'run_id':self.job['run_id']})[0],404)

    def test_remote_outputs_retry_receipt_and_artifact_scope(self):
        d=self.prepare()
        with principal_scope(self.alice): d.schedule('fixture',self.job['run_id'],{'sample_id':'sample-a','data_type':'meta'})
        files=[{'path':'pipeline-artifacts/job/0/metrics.json','remote':True,'size':4}, {'path':'outputs/unrelated.txt','size':8}]
        with patch('web_bridge.adapters.bioagent.BioAgentHost.list_files',return_value=files):
            reply=d.pending('fixture')['deliveries'][0]
        self.assertEqual(reply['files'],files[:1])
        self.assertEqual(d.pending('fixture')['deliveries'],[])
        self.assertEqual(d.pending('other')['deliveries'],[])
        with self.assertRaises(ValueError):d.artifact('other',reply['id'],files[0]['path'])
        with self.assertRaises(ValueError):d.artifact('fixture',reply['id'],files[1]['path'])
        with self.assertRaises(ValueError):d.acknowledge('fixture',{'id':reply['id'],'lease':'bad','ok':True})
        d.acknowledge('fixture',{**reply,'ok':False,'error':'temporary network failure'})
        with d.bridge.db(True) as db:db.execute('UPDATE website_deliveries SET retry_at=0')
        retry=d.pending('fixture')['deliveries'][0]
        self.assertNotEqual(retry['lease'],reply['lease'])
        with self.assertRaises(ValueError):d.acknowledge('fixture',{**reply,'ok':True})
        d.acknowledge('fixture',{**retry,'ok':True,'receipt':{'saved':True}})
        self.assertEqual(d.pending('fixture')['deliveries'],[])
        with principal_scope(self.alice):self.assertEqual(d.status(self.job['run_id'])['deliveries'][0]['state'],'delivered')

    def test_failed_and_running_jobs_are_not_delivered(self):
        d=self.prepare()
        with principal_scope(self.alice):
            d.schedule('fixture',self.job['run_id'],{'sample_id':'sample-a','data_type':'meta'})
            self.queue.update(self.job['run_id'],'running')
            self.assertEqual(d.pending('fixture')['deliveries'],[])
            self.queue.update(self.job['run_id'],'failed')
            self.assertEqual(d.pending('fixture')['deliveries'],[])
            self.assertEqual(d.status(self.job['run_id'])['deliveries'][0]['state'],'not_delivered')

if __name__=='__main__':unittest.main()
