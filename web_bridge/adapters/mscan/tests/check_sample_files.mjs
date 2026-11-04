/** Exercise the actual Vue composable against paginated adapter responses. No live services. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repo = fileURLToPath(new URL('../../../../', import.meta.url));
const host = path.join(repo, 'resource/mscan/mscan');
const requireHost = createRequire(path.join(host, 'package.json'));
const { build } = createRequire(requireHost.resolve('vite/package.json'))('esbuild');
const source = fileURLToPath(new URL('../resources/sampleFiles.ts', import.meta.url));
const output = await build({
  stdin: { contents: `
    import { createRenderer } from 'vue';
    import { useSampleFiles } from ${JSON.stringify(source)};
    export function mountFiles() {
      const renderer=createRenderer({createComment:()=>({}),insert:()=>{},remove:()=>{},parentNode:()=>null,nextSibling:()=>null});
      let files;
      const app=renderer.createApp({setup(){files=useSampleFiles(()=> 'sample-A');return ()=>null;}});
      app.mount({});
      return {files,close:()=>app.unmount()};
    }`, resolveDir: host, loader: 'ts' },
  absWorkingDir: host, bundle: true, format: 'esm', platform: 'browser', write: false,
  alias: { vue: requireHost.resolve('vue/dist/vue.runtime.esm-bundler.js') },
  define: { 'import.meta.env': '{"VITE_API_URL":""}', 'process.env.NODE_ENV': '"test"', '__VUE_OPTIONS_API__': 'true', '__VUE_PROD_DEVTOOLS__': 'false', '__VUE_PROD_HYDRATION_MISMATCH_DETAILS__': 'false' },
  plugins: [{ name: 'test-auth', setup(builder) {
    builder.onResolve({filter:/^@\/utils\/authToken$/},()=>({path:'auth',namespace:'fixture'}));
    builder.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getAccessToken=()=>"fixture-token";'}));
  }}]
});
const { mountFiles } = await import('data:text/javascript;base64,' + Buffer.from(output.outputFiles[0].text).toString('base64'));
globalThis.window = new EventTarget();
const downloads = [], requests = [];
globalThis.document = { createElement: () => ({ click() {downloads.push(this.href);} }) };
const native = (id,kind='native_analysis_output') => ({resource_id:id,name:'report.tsv',kind});
globalThis.fetch = async (url, options) => {
  assert.equal(options.headers.Authorization, 'Bearer fixture-token');
  let data;
  if(url.includes('/received?')) data=[{id:'delivery',files:[
    {id:'a',name:'report.tsv',sha256:'identical'},
    {id:'b',name:'report.tsv',sha256:'identical'},
    {id:'a',name:'report.tsv',sha256:'identical'}
  ]}];
  else if(url.includes('/resources?')) {
    const offset=Number(new URL(url,'http://fixture').searchParams.get('offset'));
    assert.ok(offset===0||offset===3);
    data={total:6,resources:offset===0?[native('native:one'),native('native:two'),native('native:one')]:
      [native('native:one'),native('native:three','native_analysis_record'),native('source:one','source')]};
  } else if(url.endsWith('/received-ticket')) {
    const id=JSON.parse(options.body).resource_id;requests.push(id);data={token:id};
  } else throw new Error('Unexpected request: '+url);
  return {ok:true,json:async()=>({code:200,data})};
};
const { files, close } = mountFiles();
try {
  const deadline=Date.now()+5000;
  while(files.files.value.length<5&&!files.error.value&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(files.error.value,'');
  const expected=['result:delivery:a','result:delivery:b','native:one','native:two','native:three'];
  assert.deepEqual(files.files.value.map(file=>file.resource_id),expected);
  for(const file of files.files.value)await files.download(file.resource_id);
  assert.deepEqual(requests,expected);
  assert.deepEqual(downloads,expected.map(id=>'/cncb/assistant/received-download/'+encodeURIComponent(id)));
  console.log('PASS distinct same-name resources remain visible, repeated IDs collapse across pages, and each file downloads by its own ID');
} finally {close();}
