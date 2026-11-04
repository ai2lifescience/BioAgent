"""Run against a development MSCAN account with the chosen test sample."""
from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import time,json,shutil,urllib.request,argparse
parser=argparse.ArgumentParser(description="Opt-in live QC interoperability check. Runs paid model calls and remote QC, and attaches results to the selected MSCAN sample.")
parser.add_argument('--url',default='http://127.0.0.1:8848/sample/metagenomic')
parser.add_argument('--agent-url',default='http://127.0.0.1:8000')
parser.add_argument('--sample-name',default='detection_demo')
parser.add_argument('--model',default='gpt-5.6-sol')
parser.add_argument('--output',type=Path,default=Path('runtime/live-validation/bridge-interoperability'))
parser.add_argument('--resume-run',default='')
args=parser.parse_args()
out=args.output;out.mkdir(parents=True,exist_ok=True); evidence={'checks':[],'errors':[]};sessions=[];credentials=[];runs=[]
def passed(text):
 evidence['checks'].append(text);print('PASS',text,flush=True);(out/'checks.json').write_text(json.dumps(evidence,indent=2))
for _ in range(60):
 try:
  urllib.request.urlopen(args.agent_url+'/static/assistant-embed.js',timeout=2).read();break
 except Exception:time.sleep(1)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=shutil.which('google-chrome'),headless=True,args=['--no-sandbox'])
 c=b.new_context(viewport={'width':1700,'height':1050},accept_downloads=True);page=c.new_page()
 def response(r):
  if r.status not in (200,202):return
  if r.url.endswith('/website/connect'):sessions.append(r.json()['session_id'])
  if r.url.endswith('/auth/website/exchange'):credentials.append(r.json()['access_token'])
  if r.url.endswith('/run'):runs.append(r.json()['run_id'])
 page.on('response',response);page.on('pageerror',lambda e:evidence['errors'].append(str(e)))
 page.goto(args.url,wait_until='domcontentloaded')
 expect(page.get_by_text('Selected sample: '+args.sample_name,exact=False)).to_be_visible(timeout=60000)
 sample=page.url.split('sampleId=')[-1].split('&')[0];evidence['sample_id']=sample
 page.get_by_role('button',name='Ask assistant',exact=True).click();frame=page.frame_locator('iframe')
 expect(frame.locator('#send')).to_be_enabled(timeout=60000)
 if not args.resume_run:
  frame.locator('#newChat').click();expect(frame.locator('#send')).to_be_enabled(timeout=30000)
 frame.locator('#model').select_option(args.model)
 prompt=f'Live integration test. Use website_context, then website_list_resources to find the selected {args.sample_name} sample R1 FASTQ. Import that file with website_import_resource; do not ask me to upload it or use examples. Run metagenomic_read_quality_control with that single-end R1 and pipeline defaults using the configured remote Cromwell executor. Collect the actual results. Do not run other pipelines. After pipeline submission, do not make further website callbacks; I will close the page while it runs.'
 if not args.resume_run:
  frame.locator('#prompt').fill(prompt);frame.locator('#send').click()
 else:
  runs.append(args.resume_run)
 deadline=time.monotonic()+900;detached=False
 agent=args.agent_url
 while time.monotonic()<deadline:
  page.wait_for_timeout(1000)
  headers={'Authorization':'Bearer '+credentials[-1]}
  if not runs:
   jobs=c.request.get(agent+'/runs?session_id='+sessions[-1],headers=headers).json().get('runs',[])
   if not jobs:continue
   runs.append(jobs[0]['run_id'])
  job=c.request.get(agent+'/runs/'+runs[-1],headers=headers).json()
  if not detached:
   approve=frame.locator('button:enabled').filter(has_text='Approve')
   if approve.count():approve.first.click()
   events=c.request.get(agent+'/runs/'+runs[-1]+'/events?after=-1',headers=headers).json().get('events',[])
   if any(e.get('event')=='pipeline_job_status' and e.get('payload',{}).get('status')=='running' for e in events):
    passed('agent discovered and imported sample file, then submitted remote QC')
    page.goto('about:blank');detached=True;passed('host page closed while QC runs')
  if job['status'] not in ('running','queued','pending_approval'):break
 assert job['status']=='succeeded',str(job.get('error') or job.get('result',{}).get('answer'))
 evidence['run_id']=runs[-1];evidence['session_id']=sessions[-1];(out/'answer.txt').write_text(job['result'].get('answer',''))
 passed('remote QC completed with browser closed')
 page.goto(args.url.split('?')[0]+'?sampleId='+sample,wait_until='domcontentloaded')
 expect(page.get_by_role('button',name='Ask assistant',exact=True)).to_be_visible(timeout=60000)
 end=time.monotonic()+180;receipt=None
 while time.monotonic()<end:
  data=page.evaluate("async s=>(await(await fetch('/api/cncb/assistant/received?sampleId='+encodeURIComponent(s))).json())",sample)
  receipt=next((r for r in data.get('data',[]) if r['run_id']==runs[-1]),None)
  if receipt:break
  page.wait_for_timeout(2000)
 assert receipt,'MSCAN did not persist delivered results'
 evidence['delivery_id']=receipt['id'];evidence['qc']=receipt.get('qc');(out/'receipt.json').write_text(json.dumps(receipt,indent=2))
 assert len(receipt['files'])>=2 and receipt.get('qc'),receipt
 passed('MSCAN backend persisted QC files and associated them with the original sample')
 native=page.evaluate("async s=>(await(await fetch('/api/cncb/sampleInfo/getSampleQcResult?sampleId='+encodeURIComponent(s))).json())",sample)['data']
 assert native['inputReads']==receipt['qc']['InputReads']
 assert native['readsAfterQC']==receipt['qc']['ReadsAfterQC']
 assert native['readsAfterHostRemoval']==receipt['qc']['ReadsAfterHostRemoval']
 passed('native MSCAN QC metrics match delivered results')
 expect(page.get_by_role('button',name='Download files',exact=True)).to_be_visible(timeout=30000)
 assert page.get_by_role('button',name='Agent results',exact=True).count()==0
 page.screenshot(path=str(out/'received.png'),full_page=True)
 assert not evidence['errors'],evidence['errors']
 (out/'checks.json').write_text(json.dumps(evidence,indent=2));b.close()
