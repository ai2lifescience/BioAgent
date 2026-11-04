"""Browser test for the generic SDK, with no site-specific page adapter."""
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=shutil.which('google-chrome'),headless=True,args=['--no-sandbox'])
    page=browser.new_page()
    page.route('http://observer.test/**',lambda route:route.fulfill(content_type='text/html',body='<h1>Unregistered project page</h1><table><tr><th>Sample</th><th>Reads</th></tr><tr><td>Example</td><td>42</td></tr></table><input type="password" value="not-observable">'))
    page.goto('http://observer.test/')
    page.add_script_tag(path=str(Path('frontend/dist/static/assistant-embed.js').resolve()))
    page.evaluate("window.drawer=AssistantDrawer.mount({src:'http://observer.test/frame'}); window.updates=[]; const frame=document.querySelector('div').shadowRoot.querySelector('iframe'); window.frameRef=frame; frame.addEventListener('load',()=>frame.contentWindow.addEventListener('message',e=>window.updates.push(e.data)))")
    value=page.evaluate('drawer.updateContext()')
    assert 'Unregistered project page' in value['visible_text']
    assert 'not-observable' not in str(value)
    assert value['tables'][0]['visible_rows']==1
    page.evaluate("document.querySelector('h1').textContent='Changed without registration'; history.pushState({},'', '/another-page')")
    page.wait_for_timeout(1500)
    assert any('Changed without registration' in str(u.get('context',{})) for u in page.evaluate('window.updates'))
    next_value=page.evaluate('drawer.updateContext()')
    assert next_value['url'].endswith('/another-page') and next_value['revision']!=value['revision']
    page.evaluate('drawer.destroy()')
    page.evaluate("window.drawer=AssistantDrawer.mount({src:'http://observer.test/frame', adapter:{getPageContext:()=>{throw new Error('No page integration')}}})")
    fallback=page.evaluate('drawer.updateContext()')
    assert 'Changed without registration' in fallback['visible_text']
    assert fallback['structured_context_status']=='unavailable'
    page.evaluate('drawer.destroy()')
    assert page.locator('h1').inner_text()=='Changed without registration'
    browser.close()
print('PASS generic observer: no page adapter, DOM changes, route changes, table discovery, password exclusion, cleanup')
