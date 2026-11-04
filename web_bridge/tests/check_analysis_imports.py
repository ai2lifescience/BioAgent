"""Opt-in live importer checks. Writes clearly named fixture projects and sessions."""
import json,time,hashlib,argparse
from pathlib import Path
from web_bridge.ports import get_host
from web_bridge.transfer.service import Transfers
from interfaces import api
from harness.sandbox import execution_access
from tools.infrastructure.pipeline_engine import broker
from tools.infrastructure.pipeline_engine.store import JobStore,now
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--username',required=True);parser.add_argument('--evidence',default='runtime/live-validation/analysis-imports');args=parser.parse_args()
out=Path(args.evidence);out.mkdir(parents=True,exist_ok=True);evidence=[]
with get_host().identity_transaction() as db:uid=db.named_user(args.username).user_id
with get_host().user_scope(uid):
 t=Transfers();sid=api.create_session()['session_id'];api.update_session_metadata(sid,title='Bridge importer validation fixtures');access=execution_access();private=broker._owned(access.workspace(sid),access);store=JobStore(private)
 (out/'matrix-session.json').write_text(json.dumps({'session_id':sid}))
 def fixture(format,files):
  job=store.create({'pipeline_name':'bridge_import_fixture_'+format});records=[]
  for role,data in files.items():
   path=store.directory(job['job_id'])/(role+'.tsv');path.write_bytes(data)
   records.append({'name':role,'wdl_output':format+'.'+role,'workspace_path':path.relative_to(private).as_posix(),'exists':True,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
  store.update(job['job_id'],status='succeeded',finished_at=now(),result={'output_records':records})
  return 'pipeline-bundles/'+job['job_id']+'/results.zip'
 def run(op,payload):
  job=t.create(sid,'mscan',op,payload);deadline=time.monotonic()+180
  while job['state'] in ('queued','running') and time.monotonic()<deadline:time.sleep(1);job=t.status(job['transfer_id'])
  evidence.append(job);(out/'matrix.json').write_text(json.dumps(evidence,indent=2));return job
 def push(type,format,files,expected='imported',suffix=''):
  bundle=fixture(format,files);source=api.write_workspace_file(sid,format+type+'.'+('fq' if type in ('meta','shortReads') else 'fa'),b'@fixture\nACGT\n+\nIIII\n' if type in ('meta','shortReads') else b'>fixture\nACGT\n')
  slots={'R1' if type in ('meta','shortReads') else 'genome':source['path']};paths=[source['path'],bundle]
  if type=='shortReads':
   r2=api.write_workspace_file(sid,format+'R2.fq',b'@fixture\nTGCA\n+\nIIII\n');slots['R2']=r2['path'];paths.append(r2['path'])
  result=run('push',{'paths':paths,'destination':{'project':'Bridge importer fixture validation','sample':format+' '+type+' fixture'+suffix,'data_type':type,'source_slots':slots},'create_missing':True})
  assert result['state']=='succeeded',result
  report=result['result']['native_imports'][0];assert report['state']==expected,report
  assert result['result']['source_registration']['status'] in ('registered','results_only'),result
  sample=result['result']['target']['sample_id']
  found=run('search',{'query':sample});assert found['state']=='succeeded',found
  if expected=='imported':
   native=next((r for r in found['result']['resources'] if str(r.get('kind','')).startswith('native_analysis_')),next(r for r in found['result']['resources'] if r.get('kind')=='analysis_output'))
   pull=run('pull',{'resource_id':native['resource_id']});assert pull['state']=='succeeded',pull
   if native['kind']=='native_analysis_record':assert json.loads((access.workspace(sid)/pull['result']['file']['path']).read_text())['sampleId']==sample
  print('PASS',format,type,expected,'and source registration',flush=True)
  return result,bundle
 push('shortReads','metax',{'profile':b'fixture\t0\t0\t1\t1\n'})
 push('genomic','FuncAssembly',{'gene_annotations_tsv':b'gene_id\tproduct\nfixture_1\tconnector validation\n'})
 push('synthetic','FuncAssembly',{'gene_annotations_tsv':b'gene_id\tproduct\nfixture_1\tconnector validation\n'})
 push('meta','FuncReads',{'gene_annotations_tsv':b'gene_id\tproduct\nfixture_1\tconnector validation\n'})
 push('meta','AssemblyId',{'species_report_tsv':b'top1_species\tcontig_count\nUnknown\t0\n'},'incomplete',' incomplete')
 push('genomic','AssemblyId',{'species_report_tsv':b'top1_species\tcontig_count\nUnknown\t0\n','contig_report_tsv':b'contig_id\n','final_contigs_renamed':b'>fixture\nACGT\n'},'incompatible_sample_type',' mismatch')
 push('meta','UnknownExampleFormat',{'report':b'metric\tvalue\nfixture\t1\n'},'unsupported')
 valid={'summary':b'dimension\tvalue\tunique_query_count\nfamily\tfixture\t1\n','hits':b'query_id\tfamily_name\nfixture\tfixture\n'}
 good,bundle=push('genomic','TcdbAnnotatorGenome',valid)
 target=good['result']['target']
 invalid=fixture('TcdbAnnotatorGenome',{'summary':b'wrong_column\nx\n','hits':valid['hits']})
 destination={'project':target['project_id'],'sample':'Invalid annotation fixture','data_type':'genomic'}
 failed=run('push',{'paths':[invalid],'destination':destination,'create_missing':True})
 assert failed['state']=='failed',failed
 assert failed['result']['file_delivery']=='delivered',failed
 assert failed['result']['native_imports'][0]['state']=='failed',failed
 print('PASS invalid schema reports delivered files and native failure',flush=True)
 retry=t.retry(failed['transfer_id']);deadline=time.monotonic()+180
 while retry['state'] in ('queued','running') and time.monotonic()<deadline:time.sleep(1);retry=t.status(retry['transfer_id'])
 assert retry['transfer_id']==failed['transfer_id'] and retry['state']=='failed',retry
 evidence.append(retry);(out/'matrix.json').write_text(json.dumps(evidence,indent=2))
 print('PASS retry retains transfer identity and does not claim invalid results imported',flush=True)
 old=fixture('TcdbAnnotatorGenome',valid);store.update(old.split('/')[1],finished_at='2000-01-01T00:00:00+00:00')
 stale=run('push',{'paths':[old],'destination':{'project':target['project_id'],'sample':target['sample_id'],'data_type':'genomic'},'create_missing':False})
 assert stale['state']=='succeeded' and stale['result']['native_imports'][0]['state']=='superseded',stale
 print('PASS older completed output does not replace newer native result',flush=True)
 assert len(next(c for c in t.connections() if c['site_id']=='mscan')['capabilities']['native_result_importers'])>=15
 summary=b'dimension\tvalue\tunique_query_count\nfamily\tfixture\t1\n';hits=b'query_id\tfamily_name\nfixture\tfixture\n'
 for format,type in [('PhiAnnotatorGenome','genomic'),('PhiAnnotatorMetagenome','meta'),('TcdbAnnotatorMetagenome','shortReads')]:
  push(type,format,{'summary':summary,'hits':hits})
 push('meta','StrainMeta',{'profile':b'#clade_name\tNCBI_tax_id\trelative_abundance\nUNCLASSIFIED\t0\t100\n'})
 push('meta','StrainCoPTR',{'log2ptr_csv':b'genome_id,log2ptr\nfixture,0.5\n'})
 for format,roles in [('BacDef',['defense_systems','defense_genes','defense_hmmer_hits']),('BacSec',['secretion_systems','secretion_genes'])]:
  push('genomic',format,{r:b'fixture_id\tvalue\nconnector_test\t1\n' for r in roles})
 push('genomic','BacBGC',{
  'bgc_features':b'sample_id\tsequence_id\tcontig_id\tprotein_id\tdomain\thmm\ti_evalue\tpvalue\tdomain_start\tdomain_end\nfixture\tfixture\tfixture\tfixture\tfixture\tfixture\t0\t0\t1\t4\n',
  'bgc_genes':b'sample_id\tsequence_id\tcontig_id\tprotein_id\tstart\tend\tstrand\taverage_probability\tmaximum_probability\nfixture\tfixture\tfixture\tfixture\t1\t4\t+\t0\t0\n',
  'bgc_clusters':b'sample_id\tsequence_id\tcontig_id\tstart\tend\tcluster_id\tlength_bp\ttype\tedge_proximity\nfixture\tfixture\tfixture\t1\t4\tfixture\t4\tfixture\t0\n'})
 for format,role in [('ReadQc','qc_summary'),('MetagenomicQc','qc_counts')]:
  counts=b'sample\tlayout\traw_reads\tquality_dropped_reads\tunivec_core_hit_reads\treads_before_host\thost_reads\tfinal_clean_reads\nfixture\tSE\t10\t1\t0\t9\t1\t8\n' if format=='ReadQc' else b'InputReads\t10\nReadsAfterQC\t9\nReadsAfterHostRemoval\t8\n'
  push('meta',format,{role:counts,'clean_r1':b'@fixture\nACGT\n+\nIIII\n'})
