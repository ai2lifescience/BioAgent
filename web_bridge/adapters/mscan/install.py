"""Install the reference adapter with small, repeatable host hooks."""
from pathlib import Path
import argparse
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('root', nargs='?', default='resource/mscan', help='Directory containing mscan/ and mscan-app/')
args = parser.parse_args()
root = Path(args.root).resolve()
source = Path(__file__).resolve().parent
# Two native result parsers exist in MSCAN but are private polling callbacks.
# Expose narrowly scoped import entry points; do not copy their parsing logic or
# call the poller (which could start unrelated follow-up workflows).
native_hooks = (
    ('IGenomeTracingService', 'importDetectionResult', 'handleDetectionSucceeded'),
    ('IMetadataProcessService', 'importKmerDetectionResult', 'handleKmerDetectionSucceeded'),
)
services = root / 'mscan-app/mscan-database/src/main/java/com/mscan/database/service'
for service, public, handler in native_hooks:
    implementation = services / 'impl' / (service + 'Impl.java')
    if f'void {handler}(SampleTaskInfo task)' not in implementation.read_text():
        raise ValueError(f'Unsupported MSCAN native parser: {handler}; review before installing.')
panel_path = root / 'mscan/src/views/sampleProgramResults/components/ProgramResultPanel.vue'
old_panel_condition = "programKey === 'funcflow' && dataType === 'genomic'"
new_panel_condition = "programKey === 'funcflow' && (dataType === 'genomic' || dataType === 'synthetic')"
if not any(condition in panel_path.read_text() for condition in (old_panel_condition, new_panel_condition)):
    raise ValueError('Unsupported MSCAN functional-result component selection; review ProgramResultPanel.vue.')
# Fail before copying files if the host page contract has changed.
for relative, anchors in {
    'mscan/src/App.vue': ('<script setup lang="ts">', '<router-view></router-view>'),
    'mscan/src/views/sampleProgramResults/index.vue': (
        '<script setup lang="ts">', '</script>', '<div class="run-programs-callout">',
        'currentSampleId', 'activeProgramRows', 'loadSampleTree', 'refreshProgramStatuses',
        ':key="`${currentSampleId}-${activeProgram.key}-${activePathogen?.key ??'),
}.items():
    text = (root / relative).read_text()
    for anchor in anchors:
        if anchor not in text:
            raise ValueError(f'Unsupported MSCAN page structure: {relative} missing {anchor!r}')
ui = root / 'mscan/src/integrations/bioagent'
ui.mkdir(parents=True, exist_ok=True)
for feature, names in {
    'connection': ('context.ts', 'AssistantBridge.vue', 'logout.ts'),
    'resources': ('sampleFiles.ts', 'SampleFileMenu.vue'),
}.items():
    for name in names:
        shutil.copyfile(source / feature / name, ui / name)
controller = root / 'mscan-app/mscan-admin/src/main/java/com/mscan/web/controller/common/AssistantController.java'
shutil.copyfile(source / 'AssistantController.java', controller)
for feature in ('connection', 'data_transfer', 'result_importers', 'resources'):
    for adapter in sorted((source / feature).glob('*.java')):
        shutil.copyfile(adapter, controller.with_name(adapter.name))

# Remove only renamed adapter classes, including stale compiler output. Without
# this migration, an incremental Maven build can retain duplicate Spring beans.
compiled = root / 'mscan-app/mscan-admin/target/classes/com/mscan/web/controller/common'
for legacy in ('AssistantAnalysisImportService', 'AssistantImportScope',
               'AssistantNativeFilesService', 'AssistantQcImportService'):
    controller.with_name(legacy + '.java').unlink(missing_ok=True)
    (compiled / (legacy + '.class')).unlink(missing_ok=True)
    for inner in compiled.glob(legacy + '$*.class'):
        inner.unlink()
# The event now lives with the adapter; remove its former common-module copy.
event = root / 'mscan-app/mscan-common/src/main/java/com/mscan/common/event/WebsiteLogoutEvent.java'
if event.exists():
    expected = (source / 'connection/WebsiteLogoutEvent.java').read_text().replace(
        'com.mscan.web.controller.common', 'com.mscan.common.event')
    if event.read_text() != expected:
        raise ValueError('Legacy WebsiteLogoutEvent has custom changes; review before migration.')
    event.unlink()
(root / 'mscan-app/mscan-common/target/classes/com/mscan/common/event/WebsiteLogoutEvent.class').unlink(missing_ok=True)

def edit(path, change):
    data = path.read_bytes()
    newline = '\r\n' if b'\r\n' in data else '\n'
    text = data.decode().replace('\r\n', '\n')
    updated = change(text)
    result = updated.replace('\n', newline).encode()
    if result != data:
        path.write_bytes(result)

def expose_native(text, public, handler=None):
    if f'void {public}(SampleTaskInfo task)' in text:
        return text
    position = text.rfind('}')
    if position < 0:
        raise ValueError('Unsupported native service declaration.')
    method = f'    void {public}(SampleTaskInfo task);' if handler is None else f'    @Override\n    public void {public}(SampleTaskInfo task) {{ {handler}(task); }}'
    return text[:position] + '\n    /** Import existing result files without submitting or polling workflows. */\n' + method + '\n' + text[position:]

for service, public, handler in native_hooks:
    edit(services / (service + '.java'), lambda text, public=public: expose_native(text, public))
    edit(services / 'impl' / (service + 'Impl.java'), lambda text, public=public, handler=handler: expose_native(text, public, handler))

def app(text):
    if 'AssistantBridge' in text: return text
    return text.replace('    <router-view></router-view>', '    <router-view></router-view>\n    <AssistantBridge />').replace('<script setup lang="ts">', '<script setup lang="ts">\nimport AssistantBridge from "@/integrations/bioagent/AssistantBridge.vue";')

def page(text):
    if 'registerAssistantContext' in text: return text
    return text.replace('<script setup lang="ts">', '<script setup lang="ts">\nimport { registerAssistantContext } from "@/integrations/bioagent/context";').replace('</script>', '''registerAssistantContext(() => ({
  sampleId: currentSampleId.value,
  sampleName: sampleInfo.value?.sampleName,
  projectId: sampleInfo.value?.projectId,
  dataType: dataType.value,
  program: activeProgramKey.value,
  rows: activeProgramRows.value,
  filters: { keyword: keyword.value, program: selectedProgram.value }
}));
</script>''', 1)

edit(root / 'mscan/src/App.vue', app)
edit(root / 'mscan/src/views/sampleProgramResults/index.vue', page)
# Synthetic samples use the same native record family as genomic samples.
# The original page otherwise requests reads records and shows an empty result.
edit(panel_path, lambda text: text.replace(old_panel_condition, new_panel_condition))

def refresh_hook(text):
    if 'agentResultVersion' in text: return text
    return text.replace('import { registerAssistantContext }','import { registerAssistantContext, useReceivedResults }').replace(
        'registerAssistantContext(() => ({', 'const agentResultVersion = useReceivedResults(() => currentSampleId.value);\nregisterAssistantContext(() => ({').replace(
        ":key=\"`${currentSampleId}-${activeProgram.key}-${activePathogen?.key ?? ''}`\"",
        ":key=\"`${currentSampleId}-${activeProgram.key}-${activePathogen?.key ?? ''}-${agentResultVersion}`\"")
edit(root / 'mscan/src/views/sampleProgramResults/index.vue', refresh_hook)

# Migrate earlier installations: these behaviors now live in added adapter files.
# Remove only our exact old insertions, preserving unrelated host changes.
def remove_logout_patch(text):
    return text.replace('import { revokeAssistant } from "@/integrations/bioagent/logout";\n', '').replace(
        '      if (clearToken) revokeAssistant();\n', '')
edit(root / 'mscan/src/stores/modules/user.ts', remove_logout_patch)

def remove_server_logout_patch(text):
    return text.replace('casLogoutFilter(CasProperties casProperties, TokenService tokenService, org.springframework.context.ApplicationEventPublisher websiteEvents)',
                        'casLogoutFilter(CasProperties casProperties, TokenService tokenService)').replace(
        '                websiteEvents.publishEvent(new com.mscan.common.event.WebsiteLogoutEvent(user.getUserId()));\n', '')
edit(root / 'mscan-app/mscan-framework/src/main/java/com/mscan/framework/config/CasClientConfig.java', remove_server_logout_patch)

def remove_download_patch(text):
    return text.replace('                .requestMatchers(HttpMethod.GET, "/assistant/received-download/*").permitAll()\n', '')
edit(root / 'mscan-app/mscan-framework/src/main/java/com/mscan/framework/config/SecurityConfig.java', remove_download_patch)

# Put downloads beside the selected sample, across all native analysis tabs.
def sample_files(text):
    if 'SampleFileMenu' in text: return text
    return text.replace('<script setup lang="ts">', '<script setup lang="ts">\nimport SampleFileMenu from "@/integrations/bioagent/SampleFileMenu.vue";').replace(
        '<div class="run-programs-callout">', '<div class="run-programs-callout">\n                <SampleFileMenu :sample-id="currentSampleId" />', 1)
edit(root / 'mscan/src/views/sampleProgramResults/index.vue', sample_files)

def remove_qc_only_files(text):
    import re
    text=re.sub(r'import \{ useSampleFiles \} from "@/integrations/bioagent/sampleFiles";\s*', '', text)
    text=re.sub(r'const \{ files: sampleFiles, error: sampleFilesError, download: downloadSampleFile \} = useSampleFiles\(\(\) => props.sampleId\);\s*', '', text)
    text=re.sub(r'<el-dropdown v-if="sampleFiles.length".*?</el-dropdown>\s*<span v-if="sampleFilesError" role="alert">.*?</span>', '', text, flags=re.S)
    return text
edit(root / 'mscan/src/views/sampleProgramResults/components/QcResultPanel.vue', remove_qc_only_files)

def status_refresh(text):
    if 'watch(agentResultVersion' in text: return text
    return text.replace('const agentResultVersion = useReceivedResults(() => currentSampleId.value);',
        'const agentResultVersion = useReceivedResults(() => currentSampleId.value);\nwatch(agentResultVersion, () => {\n  void loadSampleTree();\n  void refreshProgramStatuses();\n});')
edit(root / 'mscan/src/views/sampleProgramResults/index.vue', status_refresh)

print("Installed MSCAN adapter: three frontend hooks and two import-only parser entry points in four backend files.")
