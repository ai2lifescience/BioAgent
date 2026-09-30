"""Browser regression for live activity in both React surfaces.

Build first: npm --prefix frontend run build
Run: python -m evals.check_live_progress_browser
Optional: --screenshots docs/images/frontend_test_2026-09-30
Uses only a local SSE fixture; never calls a model or the user's web server.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread, Event
from pathlib import Path
import json
import argparse
import shutil
from copy import deepcopy
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, unquote, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ANSWER = '# Evidence report\n\n## Findings\n\n| Evidence | Assessment |\n| --- | --- |\n| Retrieved studies | Quality reviewed |\n\n## Limitations\n\nCoverage depends on the retrieved sources.\n\n## Conclusion\n\nThe report is ready for review.'
RESULT = {'answer': ANSWER, 'status': 'ok', 'runtime': {'elapsed_seconds': 3, 'model_key': 'fixture'}, 'trace': [{'event': 'run_finished', 'data': {}}]}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'frontend/dist'), **kwargs)
    def log_message(self, *args): pass
    def json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/config': self.json({'default_model_key': 'fixture', 'default_max_turns': 20, 'models': [{'key': 'fixture', 'label': 'UI test fixture'}]})
        elif path == '/sessions': self.json({'sessions': [{'session_id': 'progress-fixture', 'title': 'Research progress'}]})
        elif path.endswith('/messages'): self.json({'messages': self.server.history.get(unquote(path.split('/')[2]), [])})
        elif path == '/workspace': self.json({'workspace': {'files': []}})
        elif path == '/runs':
            session_id = parse_qs(urlparse(self.path).query).get('session_id', [''])[0]
            self.json({'runs': [{key: value for key, value in run.items() if key != 'request'} for run in reversed(self.server.runs) if run['session_id'] == session_id]})
        elif path.startswith('/runs/') and path.endswith('/events'):
            if getattr(self.server, 'events_unavailable', False):
                self.send_error(503); return
            self.json({'events': self.server.events.get(path.split('/')[2], [])})
        else:
            if path == '/assistant': self.path = '/assistant.html'
            super().do_GET()
    def do_POST(self):
        if self.path != '/run_stream': self.send_error(404); return
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(body)
        run_id = f'fixture-{len(self.server.requests):04d}'
        run = {'run_id': run_id, 'session_id': body['session_id'], 'request': body['request'], 'created_at': run_id, 'status': 'running'}
        self.server.runs.append(run)
        frames = self.server.events.setdefault(run_id, [])
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Cache-Control', 'no-cache'); self.end_headers()
        def emit(name, data):
            frames.append({'event': name, 'payload': data})
            self.wfile.write(f'event: {name}\ndata: {json.dumps(data)}\n\n'.encode()); self.wfile.flush()
        def raw(kind, delta=None, agent=None, parent=None, structured=False):
            emit('sdk_raw_response', {'data_type': kind, 'delta': delta, 'agent': agent, 'parent_call_id': parent, 'item_id': '__fake_id__', 'content_index': 0, 'content_kind': 'structured' if structured else 'narration'})
        def tool(name, call_id, output=False):
            emit('sdk_run_item', {'name': 'tool_output' if output else 'tool_called', 'call_id': call_id, 'tool_name': name})
        try:
            raw('response.output_text.delta', 'I’ll search PubMed ')
            raw('response.output_text.delta', 'and trusted sources for supporting evidence.')
            raw('response.completed')
            tool('research_specialist', 'research')
            tool('pubmed_search', 'search')
            tool('pubmed_search', 'search', True)
            raw('response.output_text.delta', 'I’m checking study quality, ', 'research', 'research')
            raw('response.output_text.delta', 'uncertainty, and limitations.', 'research', 'research')
            raw('response.completed', agent='research', parent='research')
            tool('report_review', 'review')
            raw('response.output_text.delta', '{"assessment": "INTERNAL_REVIEW_JSON"}', 'review', 'review', True)
            raw('response.completed', agent='review', parent='review', structured=True)
            raw('response.output_text.delta', '{"markdown": "INTERNAL_DRAFT_JSON\\n# report"}', 'draft', 'draft', True)
            raw('response.completed', agent='draft', parent='draft', structured=True)
            # Final response is gated by the browser so every assertion above
            # completion proves the progress was rendered live.
            self.server.release.wait(25)
            if body['request'] == 'error':
                emit('error', {'error': 'Fixture connection failed'}); return
            tool('report_review', 'review', True)
            tool('research_specialist', 'research', True)
            raw('response.output_text.delta', ANSWER)
            raw('response.completed')
            result = {**RESULT, 'session_id': body['session_id'], 'messages': [{'role': 'user', 'content': body['request']}, {'role': 'assistant', 'content': ANSWER}]}
            run.update(status='succeeded', result=result)
            self.server.history.setdefault(body['session_id'], []).extend([
                {'role': 'user', 'text': body['request']},
                {'role': 'assistant', 'text': 'I’ll search PubMed and trusted sources for supporting evidence.'},
                {'role': 'assistant', 'text': ANSWER, 'result': result},
            ])
            emit('result', result)
        except (BrokenPipeError, ConnectionResetError): pass

def check_browser(OUT):
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.release = Event(); server.requests = []
    server.history = {}; server.runs = []; server.events = {}
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    checks = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('google-chrome'), headless=True, args=['--no-sandbox', '--no-proxy-server'])
            for name, route, viewport in [('desktop', '/', {'width': 1440, 'height': 1000}), ('mobile', '/', {'width': 390, 'height': 844}), ('compact', '/assistant', {'width': 440, 'height': 900})]:
                server.release.clear()
                server.history = {}; server.runs = []; server.events = {}
                page = browser.new_page(viewport=viewport)
                page_errors = []; page.on('pageerror', lambda error: page_errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}{route}')
                page.locator('textarea').fill('Search PubMed and trusted sources. Review evidence and write a cited report.')
                page.locator('#send').click()
                progress = page.locator('.run-progress.is-running')
                progress.get_by_role('status').filter(has_text='Reviewing evidence').wait_for()
                assert progress.locator('.run-progress-preview').inner_text() == 'I’m checking study quality, uncertainty, and limitations.'
                assert not progress.locator('details').evaluate('(e) => e.open')
                assert page.locator('.message.assistant').count() == 0
                assert 'INTERNAL_' not in page.locator('body').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                progress.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / f'live-progress-{name}.png'), full_page=True)
                summary = progress.locator('summary'); summary.focus(); summary.press('Enter')
                assert progress.locator('details').evaluate('(e) => e.open')
                assert progress.locator('.progress-text').count() == 2
                assert 'INTERNAL_' not in progress.inner_text()
                if name == 'desktop': page.screenshot(path=str(OUT / 'live-progress-expanded.png'), full_page=True)
                summary.press('Enter')
                server.release.set()
                page.locator('.message.assistant h1').filter(has_text='Evidence report').wait_for()
                assert page.locator('.message.assistant').count() == 1
                assert page.locator('.message.assistant table').count() == 1
                assert page.locator('.run-progress.is-running').count() == 0
                assert not page.locator('.run-progress.is-finished details').evaluate('(e) => e.open')
                page.locator('.run-progress.is-finished summary').click()
                assert page.locator('.progress-text').count() == 2
                assert ANSWER not in page.locator('.run-progress.is-finished').inner_text()
                assert page.locator('#send').is_enabled()
                assert not page_errors, page_errors
                page.locator('.run-progress.is-finished summary').click()
                if name == 'desktop': page.screenshot(path=str(OUT / 'live-progress-completed.png'), full_page=True)
                checks.append({'viewport': name, 'route': route, 'live_before_result': True, 'no_json': True, 'separate_narration': True, 'keyboard_toggle': True, 'one_final_report': True, 'activity_retained': True, 'no_overflow': True, 'page_errors': page_errors})
                if route == '/':
                    request_count = len(server.requests)
                    page.reload()
                    page.locator('.message.assistant h1').filter(has_text='Evidence report').wait_for()
                    assert page.locator('.message.assistant').count() == 1
                    assert not page.locator('.run-progress-details').evaluate('(e) => e.open')
                    assert 'supporting evidence' not in page.locator('.message-body').last.inner_text()
                    page.locator('.run-progress-details summary').click()
                    assert page.locator('.progress-text').count() == 2
                    assert page.locator('.progress-tool').count() == 3
                    assert 'INTERNAL_' not in page.locator('body').inner_text()
                    assert page.locator('.message.assistant table').count() == 1
                    assert len(server.requests) == request_count  # Reload never reruns the model.
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(OUT / f'live-progress-reloaded-{name}.png'), full_page=True)
                    checks.append({'viewport': name, 'reload': True, 'activity_restored_from_events': True, 'no_progress_bubbles': True, 'one_final_report': True, 'no_model_rerun': True})
                    # An independent browser context must restore the same
                    # activity without relying on a local-storage text cache.
                    fresh = browser.new_page(viewport=viewport)
                    fresh.goto(f'http://127.0.0.1:{server.server_port}/')
                    fresh.locator('.run-progress-details summary').wait_for()
                    assert fresh.locator('.message.assistant').count() == 1
                    assert fresh.locator('.progress-text').count() == 2
                    fresh.close()
                    if name == 'desktop':
                        run = server.runs[-1]
                        second = deepcopy(run)
                        second.update(run_id='fixture-repeat', created_at='z-later')
                        server.runs.append(second)
                        second_frames = deepcopy(server.events[run['run_id']])
                        for frame in second_frames:
                            if frame['payload'].get('delta') == 'I’ll search PubMed ':
                                frame['payload']['delta'] = 'I’ll review evidence '
                        server.events[second['run_id']] = second_frames
                        turn = deepcopy(server.history['progress-fixture'])
                        turn[1]['text'] = 'I’ll review evidence and trusted sources for supporting evidence.'
                        server.history['progress-fixture'].extend(turn)
                        page.reload()
                        page.locator('.message.assistant').nth(1).wait_for()
                        assert page.locator('.message.assistant').count() == 2
                        activities = page.locator('.run-progress.is-finished')
                        assert activities.nth(0).locator('.progress-text').first.text_content().startswith('–I’ll search PubMed ')
                        assert activities.nth(1).locator('.progress-text').first.text_content().startswith('–I’ll review evidence ')
                        assert activities.nth(0).locator('.progress-tool').count() == 3
                        assert activities.nth(1).locator('.progress-tool').count() == 3
                        checks.append({'repeated_prompt_and_answer': True, 'activity_matched_to_correct_turn': True})
                        # Simulate archived events from the old worker, which
                        # dropped scope metadata and could contain mixed JSON.
                        for frames in server.events.values():
                            for frame in frames:
                                frame['payload'].pop('content_kind', None)
                        page.reload()
                        page.locator('.message.assistant').nth(1).wait_for()
                        assert page.locator('.progress-text').count() == 2
                        assert page.locator('.progress-tool').count() == 6
                        assert 'INTERNAL_' not in page.locator('.run-progress').all_text_contents()[0]
                        checks.append({'legacy_events': True, 'saved_narration_restored': True, 'unsafe_deltas_excluded': True})
                        server.events_unavailable = True
                        page.reload()
                        page.locator('.message.assistant').nth(1).wait_for()
                        assert page.locator('.progress-text').count() == 2
                        assert page.locator('.message.assistant table').count() == 2
                        assert page.locator('.error-banner').count() == 0
                        checks.append({'unavailable_events': True, 'saved_narration_and_reports_preserved': True})
                        server.events_unavailable = False
                page.close()
            for route in ['/', '/assistant']:
                for mode in ['stop', 'error']:
                    server.release.clear()
                    server.history = {}; server.runs = []; server.events = {}
                    page = browser.new_page()
                    page.goto(f'http://127.0.0.1:{server.server_port}{route}')
                    page.locator('textarea').fill(mode); page.locator('#send').click()
                    page.locator('.run-progress-status').filter(has_text='Reviewing evidence').wait_for()
                    if mode == 'stop': page.locator('#stop' if route == '/assistant' else '#send.stop').click()
                    else: server.release.set()
                    page.locator('.message.assistant').wait_for()
                    assert page.locator('#send').is_enabled()
                    assert page.locator('.run-progress.is-finished').count() == 1
                    assert page.locator('.run-progress.is-running').count() == 0
                    assert ('Stopped waiting' if mode == 'stop' else 'Fixture connection failed') in page.locator('.message.assistant').inner_text()
                    checks.append({'route': route, 'outcome': mode, 'activity_retained': True, 'composer_unlocked': True})
                    server.release.set(); page.close()
            browser.close()
    finally:
        server.release.set(); server.shutdown(); server.server_close(); thread.join(2)
    (OUT / 'live-progress-checks.json').write_text(json.dumps({'method': 'Local SSE fixture through the built React app; no paid API/model call', 'checks': checks}, indent=2) + '\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path, help='Keep screenshots and the result JSON in this directory')
    options = parser.parse_args()
    with TemporaryDirectory(prefix='bioagent-progress-') as temporary:
        check_browser(options.screenshots or Path(temporary))
