"""Approval-to-completion UI regression using local SSE fixtures, without model calls.

Build first: npm --prefix frontend run build
Run: python -m evals.check_pipeline_completion_browser
"""
import json
import shutil
from http.server import ThreadingHTTPServer
from threading import Event, Thread

from playwright.sync_api import sync_playwright
from evals.check_live_progress_browser import Handler

ANSWER = 'Pipeline completed successfully. Verified results are ready.'
PIPELINE = 'metagenomic_read_quality_control'
PLAN = {'pipeline_name': PIPELINE, 'engine': 'wdl', 'wdl_engine': 'cromwell',
        'inputs': {'read1': [{'path': 'uploads/qc_demo.fastq.gz', 'sha256': 'a' * 64}]},
        'parameters': {}, 'dry_run': False}


class PipelineHandler(Handler):
    def do_POST(self):
        if self.path not in {'/run_stream', '/approve_stream'}:
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, body))
        session_id = body['session_id']
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        frames = self.server.events.setdefault('pipeline-fixture', [])

        def emit(event, payload):
            frames.append({'event': event, 'payload': payload})
            self.wfile.write(f'event: {event}\ndata: {json.dumps(payload)}\n\n'.encode())
            self.wfile.flush()

        if self.path == '/run_stream':
            result = {'session_id': session_id, 'status': 'pending_approval', 'answer': 'Review this pipeline.',
                      'approval_required': True, 'approvals': [{'approval_id': 'review', 'tool_name': 'pipeline_shell',
                      'arguments': {'commands': ['agent-pipeline run --plan-id fixture']}, 'plan': PLAN}]}
            self.server.history[session_id] = [{'role': 'user', 'text': body['request']}]
            self.server.runs.append({'run_id': 'pipeline-fixture', 'session_id': session_id,
                                    'status': 'pending_approval', 'result': result})
            emit('result', result)
            return
        assert body['approved'] is True
        self.server.runs[-1].update(status='running', result=None)
        emit('approval_decision', {'approved': True, 'approval_id': 'review', 'tool_name': 'pipeline_shell',
                                  'arguments': {'commands': ['agent-pipeline run --plan-id fixture']}, 'plan': PLAN})
        status = {'job_id': 'fixture', 'pipeline_name': PIPELINE, 'status': 'running'}
        emit('pipeline_job_status', status)
        emit('log', {'message': '[agents] Agent finished: Pipeline2Agent.'})
        self.server.release.wait(25)
        emit('pipeline_job_status', {**status, 'status': 'succeeded'})
        result = {'session_id': session_id, 'status': 'ok', 'answer': ANSWER + '\n\nOutputs: [internal path].',
                  'approval_decision': {'approved': True, 'approval_id': 'review', 'tool_name': 'pipeline_shell',
                                        'arguments': {'commands': ['agent-pipeline run --plan-id fixture']}, 'plan': PLAN},
                  'workspace_files': [{'path': 'results.zip', 'name': 'results.zip'}],
                  'messages': [{'role': 'user', 'content': 'Run the demo pipeline.'}, {'role': 'assistant', 'content': ANSWER}]}
        self.server.runs[-1].update(status='succeeded', result=result)
        # The SDK's saved text and the public result can differ after path
        # projection. Activity must still match this completed request.
        self.server.history[session_id].append({'role': 'assistant',
            'text': ANSWER + '\n\nOutputs: runtime/agent_runs/fixture/results.zip.', 'result': result})
        emit('result', result)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), PipelineHandler)
    server.release = Event()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('google-chrome'), headless=True,
                                        args=['--no-sandbox', '--no-proxy-server'])
            for route, width in [('/', 1440), ('/', 390), ('/assistant', 440)]:
                server.release.clear()
                server.requests, server.runs = [], []
                server.history, server.events = {}, {}
                page = browser.new_page(viewport={'width': width, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}{route}')
                page.locator('textarea').fill('Run the demo pipeline.')
                page.locator('#send').click()
                page.get_by_role('button', name='Approve', exact=True).wait_for()
                plan_text = page.locator('.approval-plan pre').text_content()
                assert page.locator('.approval-plan').evaluate('(e) => e.open')
                if route == '/':
                    page.reload()
                    page.get_by_role('button', name='Approve', exact=True).wait_for()
                    assert page.locator('.approval-plan pre').text_content() == plan_text
                    assert page.get_by_role('button', name='Approve', exact=True).count() == 1
                    assert len(server.requests) == 1
                    fresh = browser.new_page(viewport={'width': width, 'height': 1000})
                    fresh.goto(f'http://127.0.0.1:{server.server_port}/')
                    fresh.get_by_role('button', name='Approve', exact=True).wait_for()
                    assert fresh.locator('.approval-plan pre').text_content() == plan_text
                    fresh.close()
                original_card = page.locator('.approval-item').element_handle()
                page.get_by_role('button', name='Approve', exact=True).click()
                running = page.locator('.run-progress.is-running')
                running.get_by_role('status').filter(has_text='metagenomic read quality control · running').wait_for()
                assert page.get_by_role('button', name='Approve', exact=True).is_disabled()
                assert not page.locator('.approval-plan').evaluate('(e) => e.open')
                page.locator('.approval-plan summary').click()
                assert page.locator('.approval-plan').evaluate('(e) => e.open')
                assert 'Pipeline running. Waiting for verified results' in page.locator('.approval-status').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if route == '/':
                    fresh = browser.new_page(viewport={'width': width, 'height': 1000})
                    fresh.goto(f'http://127.0.0.1:{server.server_port}/')
                    for _ in range(2):
                        fresh.locator('.approval-item').wait_for()
                        assert not fresh.locator('.approval-plan').evaluate('(e) => e.open')
                        assert fresh.locator('.approval-plan pre').text_content() == plan_text
                        assert fresh.get_by_role('button', name='Approve', exact=True).is_disabled()
                        assert fresh.get_by_role('button', name='Reject', exact=True).is_disabled()
                        assert 'Approved' in fresh.locator('.approval-status').inner_text()
                        fresh.reload()
                    fresh.close()
                server.release.set()
                page.locator('.message-body').filter(has_text=ANSWER).wait_for()
                page.wait_for_function("!document.querySelector('.run-progress.is-running')")
                activity = page.locator('.run-progress.is-finished').last
                activity.locator('summary').click()
                assert 'metagenomic read quality control · succeeded' in activity.inner_text()
                assert 'metagenomic read quality control · running' not in activity.inner_text()
                assert original_card.evaluate('(e) => e.isConnected && e === document.querySelector(".approval-item")')
                assert page.locator('.approval-item').count() == 1
                assert page.locator('.approval-plan').evaluate('(e) => e.open'), 'Manual expansion must survive progress updates'
                assert page.locator('.approval-plan pre').text_content() == plan_text
                assert page.locator('.approval-record').count() == 0
                assert page.locator('.message.user').count() == 1
                assert page.locator('#send').is_enabled()
                assert len(server.requests) == 2
                if route == '/':
                    page.reload()
                    page.locator('.message-body').filter(has_text=ANSWER).wait_for()
                    activity = page.locator('.run-progress.is-finished').last
                    activity.locator('summary').click()
                    assert 'metagenomic read quality control · succeeded' in activity.inner_text()
                    assert page.locator('.message.assistant').count() == 2
                    assert page.locator('.approval-item').count() == 1
                    assert not page.locator('.approval-plan').evaluate('(e) => e.open')
                    page.locator('.approval-plan summary').focus()
                    page.keyboard.press('Enter')
                    assert page.locator('.approval-plan').evaluate('(e) => e.open')
                    assert page.locator('.approval-plan pre').text_content() == plan_text
                    assert page.get_by_role('button', name='Approve', exact=True).is_disabled()
                    assert page.get_by_role('button', name='Reject', exact=True).is_disabled()
                    assert page.locator('.message.assistant').first.locator('.approval-item').count() == 1
                    assert page.locator('.message.assistant').last.locator('.approval-item').count() == 0
                    assert len(server.requests) == 2
                assert not errors, errors
                print(f'approval progress, automatic completion, saved activity: {route} at {width}px: ok')
                page.close()
            # Legacy history can contain only the saved decision, without
            # runtime/evidence fields. It must still render a read-only box.
            for approved in [True, False]:
                server.runs = []
                server.history = {'progress-fixture': [{'role': 'assistant', 'text': 'Saved decision.',
                    'result': {'approval_decision': {'approved': approved, 'tool_name': 'pipeline_shell',
                                                    'arguments': {}, 'plan': PLAN}}}]}
                page = browser.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                for _ in range(2):
                    card = page.locator('.approval-item')
                    card.wait_for()
                    assert ('Approved' if approved else 'Rejected') in card.inner_text()
                    assert not card.locator('.approval-plan').evaluate('(e) => e.open')
                    card.locator('.approval-plan summary').click()
                    assert card.locator('.approval-plan').evaluate('(e) => e.open')
                    assert card.locator('button').count() == 2
                    assert card.get_by_role('button', name='Approve', exact=True).is_disabled()
                    assert card.get_by_role('button', name='Reject', exact=True).is_disabled()
                    page.reload()
                page.close()
            browser.close()
    finally:
        server.release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


if __name__ == '__main__':
    main()
