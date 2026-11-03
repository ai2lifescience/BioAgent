"""Exercise the built UI with overlapping durable jobs, without model/tool calls.

Build: npm --prefix frontend run build
Run: python -m evals.check_web_multitasking (requires Playwright and Chrome)
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Event
from urllib.parse import urlparse, parse_qs
import json
import shutil
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'frontend/dist'), **kwargs)

    def log_message(self, *args):
        pass

    def json(self, payload, code=200):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        state = self.server
        if path == '/auth/status':
            self.json({'mode': 'local', 'user': {'id': 'fixture', 'name': 'Fixture'}})
        elif path == '/config':
            self.json({'default_model_key': 'fixture', 'default_max_turns': 20, 'models': [{'key': 'fixture'}], 'storage_limits': {'file_bytes': 1024, 'upload_chunk_bytes': 4},
                       'capabilities': {'tools': {}, 'pipelines': {}, 'quick_starts': {
                           'PDB structure viewer': {'status': 'available', 'reason': ''},
                           'Knowledge ingest and retrieve': {'status': 'needs_configuration', 'reason': 'Configure embedding credentials.'}}}})
        elif path == '/sessions':
            self.json({'sessions': [{'session_id': sid, 'title': sid, 'message_count': len(state.history.get(sid, []))} for sid in state.sessions]})
        elif path.endswith('/messages'):
            self.json({'messages': state.history.get(path.split('/')[2], [])})
        elif path == '/workspace':
            self.json({'workspace': {'files': state.files.get(query['session_id'][0], [])}})
        elif path == '/runs':
            self.json({'runs': [dict(run) for run in state.runs.values() if not query.get('session_id') or run['session_id'] == query['session_id'][0]]})
        elif path.startswith('/runs/') and path.endswith('/events'):
            run_id = path.split('/')[2]
            if state.disconnect:
                self.json({'error': 'Temporary network failure'}, 503)
                return
            after = int(query.get('after', [-1])[0])
            state.cursors.append(after)
            self.json({'run': dict(state.runs[run_id]), 'events': [event for event in state.events[run_id] if event['sequence'] > after]})
        else:
            super().do_GET()

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
        state = self.server
        if self.path == '/sessions':
            sid = f'chat-{len(state.sessions) + 1}'
            state.sessions.append(sid)
            self.json({'session_id': sid})
        elif self.path == '/run':
            sid = payload['session_id']
            assert not any(run['session_id'] == sid and run['status'] in ('queued', 'running', 'pending_approval') for run in state.runs.values())
            state.submissions.append(payload)
            rid = f'run-{len(state.submissions)}'
            state.history.setdefault(sid, []).append({'role': 'user', 'text': payload['request']})
            state.runs[rid] = {'run_id': rid, 'session_id': sid, 'status': 'running' if len(state.submissions) <= 2 else 'queued'}
            state.events[rid] = [{'sequence': 0, 'event': 'sdk_raw_response', 'payload': {
                'data_type': 'response.output_text.delta', 'content_kind': 'narration', 'delta': f'Progress for {sid}.', 'item_id': rid}}]
            self.json(state.runs[rid], 202)
        elif self.path == '/workspace/uploads':
            state.upload = {**payload, 'upload_id': 'upload-1', 'offset': 0}
            self.json(state.upload)
        elif self.path == '/workspace/uploads/upload-1/complete':
            state.upload_release.wait(15)
            file = {'path': 'uploads/' + state.upload['filename'], 'name': state.upload['filename'], 'size': state.upload['size']}
            state.files.setdefault(state.upload['session_id'], []).append(file)
            self.json({'files': [file]})
        elif self.path == '/approve_async':
            state.approvals.append(payload)
            run = next(run for run in state.runs.values() if run['session_id'] == payload['session_id'])
            run.update(status='running', result=None)
            self.json(run, 202)
        else:
            self.json({'error': 'Unexpected POST ' + self.path}, 404)

    def do_PATCH(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        assert int(self.headers['Upload-Offset']) == self.server.upload['offset']
        self.server.upload['offset'] += len(data)
        self.json(self.server.upload)

def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.sessions = ['chat-1', 'chat-2']
    server.history, server.runs, server.events, server.files = {}, {}, {}, {}
    server.submissions, server.approvals, server.cursors = [], [], []
    server.disconnect = False
    server.upload_release = Event()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def finish(rid, answer, approval=False, failure=False):
        run = server.runs[rid]
        sid = run['session_id']
        result = {'answer': answer, 'session_id': sid, 'status': 'pending_approval' if approval else 'ok'}
        if approval:
            result.update(approval_required=True, approvals=[{'approval_id': 'review-1', 'tool_name': 'fixture_operation', 'arguments': {}}])
        else:
            server.files[sid] = [{'path': f'outputs/{sid}.txt', 'name': f'{sid}.txt', 'size': 10}]
            result['workspace_files'] = server.files[sid]
            server.history[sid].append({'role': 'assistant', 'text': answer, 'result': result})
        run.update(status='pending_approval' if approval else 'failed' if failure else 'succeeded', result=None if failure else result, error=answer if failure else None)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=shutil.which('google-chrome'), headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            pane = lambda sid: page.locator(f'.conversation-pane[data-session-id="{sid}"]')
            row = lambda sid: page.locator(f'.session-row[data-session-id="{sid}"]')
            select = lambda sid: row(sid).locator('.session-button').click()
            def send(sid, text):
                pane(sid).get_by_role('textbox', name='Message Pipeline2Agent').fill(text)
                pane(sid).get_by_role('button', name='Send message', exact=True).click()
                expect(row(sid).locator('.session-run-status')).to_have_text('Running' if len(server.submissions) <= 2 else 'Queued')

            expect(pane('chat-1').get_by_text('Quick starts', exact=True)).to_be_visible()
            expect(pane('chat-1').get_by_role('button', name='PDB structure viewer Available')).to_be_visible()
            expect(pane('chat-1').get_by_role('button', name='Knowledge ingest and retrieve Configure embedding credentials.')).to_be_enabled()
            for _ in range(3):
                page.get_by_role('button', name='New chat', exact=True).click()
            expect(row('chat-1')).to_have_class('session-row active')
            assert len(server.sessions) == 2, 'Repeated New chat must reuse the selected empty conversation'
            send('chat-1', 'First independent request')
            pane('chat-1').get_by_role('textbox', name='Message Pipeline2Agent').fill('Draft for chat one')
            expect(row('chat-1').locator('.session-more')).to_be_disabled()
            page.get_by_role('button', name='New chat', exact=True).click()
            expect(row('chat-2')).to_have_class('session-row active')
            assert len(server.sessions) == 2, 'Reuse an existing empty chat while another runs'
            expect(pane('chat-2').get_by_role('textbox', name='Message Pipeline2Agent')).to_have_value('')
            expect(pane('chat-2').get_by_role('button', name='Upload files', exact=True)).to_be_enabled()
            send('chat-2', 'Second independent request')
            pane('chat-2').get_by_role('textbox', name='Message Pipeline2Agent').fill('Draft for chat two')
            # Resolve the first request while the second conversation is selected.
            finish('run-1', 'Only chat one answer')
            expect(row('chat-1').locator('.session-run-status')).to_have_text('Completed')
            expect(pane('chat-2')).not_to_contain_text('Only chat one answer')
            select('chat-1')
            expect(pane('chat-1')).to_contain_text('Only chat one answer')
            expect(pane('chat-1')).to_contain_text('chat-1.txt')
            expect(pane('chat-1').get_by_role('textbox', name='Message Pipeline2Agent')).to_have_value('Draft for chat one')
            expect(pane('chat-1')).not_to_contain_text('Second independent request')
            select('chat-2')
            expect(pane('chat-2').get_by_role('textbox', name='Message Pipeline2Agent')).to_have_value('Draft for chat two')
            select('chat-1')
            pane('chat-1').locator('input[type=file]').last.set_input_files({'name': 'chat-one-upload.txt', 'mimeType': 'text/plain', 'buffer': b'fixture'})
            expect(row('chat-1').locator('.session-run-status')).to_have_text('Uploading')
            select('chat-2')
            server.upload_release.set()
            expect(row('chat-1').locator('.session-run-status')).to_have_text('Completed')
            expect(pane('chat-2')).not_to_contain_text('chat-one-upload.txt')
            select('chat-1')
            expect(pane('chat-1')).to_contain_text('chat-one-upload.txt')
            assert server.upload['session_id'] == 'chat-1'
            # More jobs than a browser's usual per-origin connection limit.
            for number in range(3, 9):
                if number == 3:
                    page.locator('.new-chat').evaluate('(button) => { for (let i = 0; i < 8; i++) button.click(); }')
                else:
                    page.get_by_role('button', name='New chat', exact=True).click()
                if number == 3:
                    draft = pane('chat-3').get_by_role('textbox', name='Message Pipeline2Agent')
                    draft.fill('Keep this unsent draft')
                    select('chat-1')
                    page.get_by_role('button', name='New chat', exact=True).click()
                    expect(draft).to_have_value('Keep this unsent draft')
                    page.locator('.new-chat').evaluate('(button) => { for (let i = 0; i < 8; i++) button.click(); }')
                    expect(row('chat-3')).to_have_class('session-row active')
                    assert len(server.sessions) == 3, 'Do not create extra sessions for an unsent draft'
                send(f'chat-{number}', f'Queued request {number}')
            select('chat-1')
            expect(pane('chat-1').get_by_role('button', name='Refresh workspace')).to_be_enabled()
            assert len(server.submissions) == 8
            # Refresh reconnects to every unfinished job without submitting again.
            page.reload()
            expect(row('chat-2').locator('.session-run-status')).to_have_text('Running')
            expect(row('chat-8').locator('.session-run-status')).to_have_text('Queued')
            finish('run-2', 'Review chat two operation', approval=True)
            expect(row('chat-2').locator('.session-run-status')).to_have_text('Needs approval')
            select('chat-2')
            expect(pane('chat-2').get_by_role('button', name='Send message', exact=True)).to_be_disabled()
            pane('chat-2').get_by_role('button', name='Approve', exact=True).click()
            expect(row('chat-2').locator('.session-run-status')).to_have_text('Running')
            select('chat-1')
            finish('run-2', 'Approved chat two result')
            expect(row('chat-2').locator('.session-run-status')).to_have_text('Completed')
            expect(pane('chat-1')).not_to_contain_text('Approved chat two result')
            select('chat-2')
            expect(pane('chat-2')).to_contain_text('Approved chat two result')
            assert len(server.approvals) == 1
            server.disconnect = True
            select('chat-3')
            expect(pane('chat-3')).to_contain_text('Connection interrupted.')
            expect(pane('chat-3').get_by_role('button', name='Send message', exact=True)).to_have_count(0)
            select('chat-1')
            expect(pane('chat-1').get_by_role('button', name='Send message', exact=True)).to_be_enabled()
            server.disconnect = False
            finish('run-3', 'Fixture job failed', failure=True)
            expect(row('chat-3').locator('.session-run-status')).to_have_text('Failed')
            select('chat-3')
            expect(pane('chat-3')).to_contain_text('Fixture job failed')
            expect(pane('chat-3').get_by_role('button', name='Send message', exact=True)).to_be_enabled()
            assert len(server.submissions) == 8, 'Recovery must never POST another task'
            assert any(cursor >= 0 for cursor in server.cursors), 'Must resume event reads after the cursor'
            assert not errors, errors
            # Check the same navigation on a narrow viewport.
            page.set_viewport_size({'width': 390, 'height': 844})
            pane('chat-3').get_by_role('button', name='Open navigation').click()
            select('chat-8')
            expect(pane('chat-8')).to_be_attached()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            browser.close()
            print('PASS: concurrent chats, drafts, result/file isolation, eight jobs, reload recovery, approvals, reconnect, failure, mobile navigation; no model calls.')
    finally:
        server.upload_release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


if __name__ == '__main__':
    main()
