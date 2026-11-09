import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock
from tools.function_tools.website.page import website_import_resource, website_import_data
from agents.tool_context import ToolContext

class ResourceTests(unittest.TestCase):
    def test_csv_export_returns_owned_artifact_not_upload_receipt(self):
        file={'path':'uploads/export.csv','workspace_path':'uploads/export.csv','name':'export.csv','size':4,'kind':'table','content_type':'text/csv','modified_at':123}
        receipt={k:v for k,v in file.items() if k!='modified_at'}
        receipt.update(session_id='owned-session',sha256='checksum')
        class Host:
            def publish_text(self,*args):return receipt
            def list_files(self,session):
                async def files():return [file]
                return asyncio.run(files())
        context=ToolContext(context=SimpleNamespace(session_id='owned-session',execution_access=None,website_binding={'binding_id':'binding','token':'test'}),tool_name='website_import_data',tool_call_id='test',tool_arguments='{}')
        bridge=MagicMock();bridge.get_binding.return_value={'site_id':'test','context':{'revision':'1'}}
        with patch('tools.function_tools.website.page.get_host',return_value=Host()),patch('tools.function_tools.website.page.get_bridge',return_value=bridge),patch('web_bridge.conversations.WebsiteAccounts'),patch('tools.function_tools.website.page._call',new=AsyncMock(return_value={'filename':'export.csv','content':'a\n1\n'})):
            value=asyncio.run(website_import_data.on_invoke_tool(context,json.dumps({'resource_id':'table'})))
        result=json.loads(str(value))
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['files'],[file])
        self.assertNotIn('sha256',result['files'][0])

    def test_import_verification_runs_sync_workspace_adapter_outside_event_loop(self):
        file={'path':'uploads/test.fq.gz','workspace_path':'uploads/test.fq.gz','name':'test.fq.gz','size':12,'kind':'upload','content_type':'application/gzip','modified_at':123}
        class Host:
            def list_files(self,session):
                # The real isolated workspace adapter also owns an asyncio runner.
                async def files(): return [file]
                return asyncio.run(files())
        context=ToolContext(context=SimpleNamespace(session_id='owned-session'),tool_name='website_import_resource',tool_call_id='test',tool_arguments='{}')
        with patch('tools.function_tools.website.page.get_host',return_value=Host()), patch('tools.function_tools.website.page._call',new=AsyncMock(return_value={'file':file})):
            result=asyncio.run(website_import_resource.on_invoke_tool(context,json.dumps({'resource_id':'source:meta:sample:R1'})))
        self.assertIn('uploads/test.fq.gz',str(result))
        self.assertNotIn('asyncio.run() cannot',str(result))

    def test_callback_cannot_invent_a_workspace_file(self):
        context=ToolContext(context=SimpleNamespace(session_id='owned-session'),tool_name='website_import_resource',tool_call_id='test',tool_arguments='{}')
        host=SimpleNamespace(list_files=lambda session:[])
        with patch('tools.function_tools.website.page.get_host',return_value=host),patch('tools.function_tools.website.page._call',new=AsyncMock(return_value={'file':{'path':'other-user/secret'}})):
            result=asyncio.run(website_import_resource.on_invoke_tool(context,json.dumps({'resource_id':'source'})))
        self.assertIn('did not publish',str(result))

if __name__=='__main__':unittest.main()
