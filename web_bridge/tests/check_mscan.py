"""Opt-in live MSCAN bridge acceptance test. Uses a running, authenticated MSCAN.

With the development login bypass enabled, no browser credentials are needed.
This test submits paid model requests; --pipeline also submits the bundled WDL
template to the configured executor. Evidence contains no authentication tokens.
"""
import argparse
import json
from pathlib import Path
import shutil
import time

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8848/sample/metagenomic')
    parser.add_argument('--agent-url', help='Override the config response in this browser only, for a cross-site embedding test.')
    parser.add_argument('--model', default='gpt-5.6-sol')
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--pipeline-only', action='store_true', help='Only run the remote workflow and logout checks.')
    parser.add_argument('--detach', action='store_true', help='Close the host page once the remote workflow is running, then restore it.')
    parser.add_argument('--output', type=Path, default=Path('runtime/live-validation/mscan-bridge-final'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {'checks': [], 'errors': []}
    sessions, credentials = [], []  # Credentials stay in this process, never in evidence.

    def passed(name):
        evidence['checks'].append(name)
        print('PASS', name, flush=True)
        (args.output / 'checks.json').write_text(json.dumps(evidence, indent=2))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('google-chrome'), headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1700, 'height': 1050}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: evidence['errors'].append(str(error)))
        def response(result):
            if result.status != 200: return
            if result.url.endswith('/website/connect'): sessions.append(result.json()['session_id'])
            if result.url.endswith('/auth/website/exchange'):
                payload = result.json()
                if payload.get('access_token'): credentials.append(payload['access_token'])
        page.on('response', response)
        if args.agent_url:
            def config(route):
                result = route.fetch()
                payload = result.json(); payload['data']['agentUrl'] = args.agent_url
                route.fulfill(response=result, json=payload)
            page.route('**/assistant/config?*', config)

        def open_assistant():
            page.get_by_role('button', name='Ask assistant', exact=True).click(timeout=60000)
            frame = page.frame_locator('iframe')
            expect(frame.locator('#send')).to_be_enabled(timeout=60000)
            return frame

        def send(frame, prompt):
            frame.locator('#model').select_option(args.model)
            frame.locator('#prompt').fill(prompt); frame.locator('#send').click()
            expect(frame.locator('#messages')).to_contain_text(prompt, timeout=10000)

        page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
        frame = open_assistant()
        assert credentials, 'Embedded sign-in did not return an in-memory credential'
        assert not any(cookie['name'] == 'bioagent_session' for cookie in context.cookies()), 'Embedding unexpectedly set a login cookie'
        passed('cookie-free website sign-in')
        if not args.pipeline_only:
            frame.locator('#newChat').click()
            expect(frame.locator('#send')).to_be_enabled(timeout=30000)
            send(frame, 'Bridge acceptance test: read qc_summary and qc_chart from this website. Give input, after-QC, after-host-removal read counts and retention percentage. Import qc_summary as CSV, then use report_write to create a short Markdown QC report with those counts and the source revision. Return the actual CSV and report paths. Do not run any pipeline or modify MSCAN data.')
            expect(frame.locator('#send')).to_be_enabled(timeout=240000)
            text = frame.locator('body').inner_text(); (args.output / 'qc-report.txt').write_text(text)
            assert '4168' in text.replace(',', '') and '.csv' in text and '.md' in text, text[-2000:]
            passed('live website table, chart, CSV import and report generation')
            before = sessions[-1]
            page.reload(wait_until='domcontentloaded'); frame = open_assistant()
            expect(frame.get_by_text('Bridge acceptance test:', exact=False).first).to_be_visible(timeout=30000)
            assert sessions[-1] == before
            passed('same conversation and messages restored after reload')
            agent_url = args.agent_url or page.locator('iframe').get_attribute('src').split('/assistant')[0]
            send(frame, 'Use the backend website connector to find detection_demo in MSCAN and pull its R1 FASTQ into this session. Do not run a pipeline.')
            expect(frame.locator('#send')).to_be_enabled(timeout=240000)
            headers = {'Authorization': 'Bearer ' + credentials[-1]}
            workspace = context.request.get(agent_url + '/workspace?session_id=' + sessions[-1], headers=headers).json()
            files = workspace.get('workspace', workspace).get('files', [])
            file = next(f for f in files if 'detection_demo' in (f.get('name') or f.get('path', '')))
            path = file.get('workspace_path') or file['path']
            from urllib.parse import urlencode
            download = context.request.get(agent_url + '/workspace/file?' + urlencode({'session_id':sessions[-1], 'path':path}), headers=headers)
            assert download.status == 200 and len(download.body()) == file['size']
            passed('natural-language MSCAN source import and authenticated download')
            assert frame.get_by_role('button', name='Send to website / delivery status').count() == 0
            with page.expect_download(timeout=30000) as pending:
                frame.locator('a[href*="workspace/file"]:visible').filter(has_text='.md').first.click()
            assert Path(pending.value.path()).stat().st_size > 0
            passed('embedded assistant artifact download without cookies')
            previous_logins = len(credentials)
            page.locator('iframe').content_frame.locator('body').evaluate("() => window.dispatchEvent(new Event('bioagent-auth-expired'))")
            deadline = time.monotonic() + 30
            while len(credentials) == previous_logins and time.monotonic() < deadline: page.wait_for_timeout(200)
            expect(frame.locator('#send')).to_be_enabled(timeout=30000)
            assert len(credentials) > previous_logins and sessions[-1] == before
            passed('embedded sign-in renewal reconnects the same conversation')
            send(frame, 'Write a detailed explanation of how medians differ from means, with five worked examples. Do not use tools.')
            expect(frame.locator('#stop')).to_be_enabled(timeout=30000)
            with page.expect_response('**/runs/*/cancel') as cancelled:
                frame.locator('#stop').click()
            cancel_result = cancelled.value.json()
            expect(frame.locator('#send')).to_be_enabled(timeout=60000)
            agent_url = args.agent_url or page.locator('iframe').get_attribute('src').split('/assistant')[0]
            terminal = context.request.get(agent_url + '/runs/' + cancel_result['run_id'], headers={'Authorization':'Bearer ' + credentials[-1]}).json()
            assert terminal['status'] == 'cancelled', terminal['status']
            passed('Stop cancels the actual server run')
        if args.pipeline or args.pipeline_only:
            frame.locator('#newChat').click(); expect(frame.locator('#send')).to_be_enabled(timeout=30000)
            agent_url = args.agent_url or page.locator('iframe').get_attribute('src').split('/assistant')[0]
            send(frame, 'Run template_wdl with its bundled example data and collect the results. Use the configured remote Cromwell executor. Do not use any uploaded sample files or other pipelines.')
            deadline = time.monotonic() + 300
            detached = False
            while time.monotonic() < deadline:
                page.wait_for_timeout(1000)
                available = frame.locator('button:enabled').filter(has_text='Approve')
                if available.count(): available.first.click()
                if args.detach and not detached:
                    headers = {'Authorization': 'Bearer ' + credentials[-1]}
                    jobs = context.request.get(agent_url + '/runs?session_id=' + sessions[-1], headers=headers).json()['runs']
                    if jobs:
                        job = jobs[0]
                        events = context.request.get(agent_url + '/runs/' + job['run_id'] + '/events?after=-1', headers=headers).json()['events']
                        running = any(event.get('event') == 'pipeline_job_status' and event.get('payload', {}).get('status') in ('running', 'queued') for event in events)
                        if running and job['status'] == 'running':
                            page.goto('about:blank'); detached = True
                            while time.monotonic() < deadline:
                                job = context.request.get(agent_url + '/runs/' + job['run_id'], headers=headers).json()
                                if job['status'] not in ('queued', 'running'): break
                                page.wait_for_timeout(1000)
                            assert job['status'] == 'succeeded', job['status']
                            page.goto(args.url, wait_until='domcontentloaded'); frame = open_assistant()
                            passed('remote workflow finishes with the MSCAN page closed and restores results')
                if frame.locator('#send').is_enabled(): break
            if args.detach: assert detached, 'The test did not observe a running remote workflow before completion'
            expect(frame.locator('#send')).to_be_enabled(timeout=10000)
            (args.output / 'template-result.txt').write_text(frame.locator('body').inner_text())
            expect(frame.locator('a[href*="workspace/file"]').filter(has_text='metrics.json').first).to_be_visible(timeout=30000)
            with page.expect_download(timeout=60000) as pending:
                frame.locator('a[href*="workspace/file"]').filter(has_text='metrics.json').first.click()
            metrics = json.loads(Path(pending.value.path()).read_text())
            assert isinstance(metrics, dict) and metrics
            (args.output / 'template-metrics.json').write_text(json.dumps(metrics, indent=2))
            passed('remote template WDL completion and files available in embedded assistant')
        page.screenshot(path=str(args.output / 'integration.png'), full_page=True)
        # Exercise host logout server-side. In the dev bypass profile a new login
        # is automatic; revocation must still invalidate the old agent credential.
        agent_url = args.agent_url or page.locator('iframe').get_attribute('src').split('/assistant')[0]
        old = credentials[-1]
        result = page.evaluate("""async () => (await (await fetch('/api/cncb/assistant/logout', {method:'POST'})).json()).code""")
        assert result == 200
        assert context.request.get(agent_url + '/sessions', headers={'Authorization': 'Bearer ' + old}).status == 401
        passed('MSCAN logout revokes its agent login')
        assert not evidence['errors'], evidence['errors']
        evidence['sessions'] = list(dict.fromkeys(sessions))
        (args.output / 'checks.json').write_text(json.dumps(evidence, indent=2))
        browser.close()


if __name__ == '__main__': main()
