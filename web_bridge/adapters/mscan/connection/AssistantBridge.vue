<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "@/stores/modules/user";
import { getAccessToken } from "@/utils/authToken";
import { assistantPage } from "./context";
import { revokeAssistant } from "./logout";

const router = useRouter(),
  user = useUserStore();
// Observe logout before the host action removes its token; no user-store patch.
const stopLogout = user.$onAction(({ name, args }) => {
  if (name === "clearAuth" && args[0] !== false) revokeAssistant();
});
const mount = ref<HTMLElement>(),
  enabled = ref(false),
  error = ref("");
let receiptVersion = "",
  resultsEpoch = 0;
const sessionId = ref("");
let drawer: any,
  timer: ReturnType<typeof setInterval> | undefined,
  config: any,
  starting = false,
  stopped = false;
const prefix = ((import.meta.env.VITE_API_URL as string) || "") + "/cncb";
function headers(json = false) {
  const token = getAccessToken();
  return { ...(json ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: "Bearer " + token } : {}) };
}
async function request(path: string, body?: unknown) {
  const response = await fetch(prefix + path, {
    method: body === undefined ? "GET" : "POST",
    headers: headers(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin"
  });
  const payload = await response.json();
  if (!response.ok || Number(payload.code) !== 200) throw new Error(payload.msg || "Assistant request failed.");
  return payload.data;
}
function revision() {
  let hash = 2166136261;
  for (const char of JSON.stringify([router.currentRoute.value.fullPath, assistantPage.value, receiptVersion]))
    hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return "mscan-" + (hash >>> 0).toString(16);
}
function snapshot() {
  const page = assistantPage.value,
    resources: any[] = [];
  if (page.sampleId && ["meta", "shortReads"].includes(page.dataType || ""))
    resources.push(
      { id: "qc_summary", kind: "table", title: "QC read counts", exportable: true },
      { id: "qc_chart", kind: "figure", title: "QC retention" }
    );
  if (page.rows?.length)
    resources.push({ id: "current_results", kind: "table", title: page.program || "Selected results", exportable: true });
  return {
    revision: revision(),
    title:
      "MSCAN · " +
      String(router.currentRoute.value.meta.title || router.currentRoute.value.name || location.pathname) +
      (page.sampleName ? " · " + page.sampleName : ""),
    page: { route: router.currentRoute.value.fullPath, name: String(router.currentRoute.value.name || "") },
    url: location.href,
    selection: {
      sample_id: page.sampleId,
      project_id: page.projectId,
      sample_name: page.sampleName,
      data_type: page.dataType,
      program: page.program
    },
    delivery_target: page.sampleId
      ? { sample_id: page.sampleId, data_type: page.dataType, sample_name: page.sampleName, project_id: page.projectId }
      : null,
    filters: page.filters || {},
    resources,
    routes: [
      { id: "home", label: "Home" },
      { id: "samples", label: "Sample results" }
    ],
    manual: { version: "1", title: "MSCAN assistant guide" }
  };
}
async function table(args: any) {
  const page = assistantPage.value;
  let rows: Record<string, unknown>[];
  if (args.resource_id === "qc_summary" && page.sampleId) {
    const qc = await request("/sampleInfo/getSampleQcResult?sampleId=" + encodeURIComponent(page.sampleId));
    rows = ["inputReads", "readsAfterQC", "readsAfterHostRemoval"].map(metric => ({ metric, reads: qc?.[metric] ?? null }));
  } else if (args.resource_id === "current_results") rows = page.rows || [];
  else throw new Error("This resource is not available on the selected page.");
  const columns = Array.from(new Set(rows.flatMap(row => Object.keys(row)))).map(name => ({
    name,
    type: rows.some(row => typeof row[name] === "number") ? "number" : "string"
  }));
  const offset = Math.max(0, Number(args.offset) || 0),
    limit = Math.max(1, Math.min(Number(args.limit) || 50, 200));
  return {
    resource_id: args.resource_id,
    title: args.resource_id,
    revision: revision(),
    columns,
    rows: rows.slice(offset, offset + limit),
    offset,
    total_rows: rows.length
  };
}
const manual = {
  section_id: "using-the-assistant",
  title: "Using the MSCAN assistant",
  version: "1",
  text: "The assistant uses the selected sample and active result tab. QC inputReads is the input count; readsAfterQC is the count after quality control; readsAfterHostRemoval is the remaining count after host removal. Null means unavailable, not zero. Ask the assistant in chat to pull sample files or push results to a named project and sample. Agent runs and downloaded artifacts remain associated with your account. Changing pages updates context; it does not cancel a running analysis."
};
async function refreshResults() {
  const requestVersion = ++resultsEpoch,
    sample = assistantPage.value.sampleId || "";
  try {
    const receipts = await request("/assistant/received?sampleId=" + encodeURIComponent(sample));
    if (requestVersion !== resultsEpoch || !user.isAuthenticated || sample !== (assistantPage.value.sampleId || "")) return;
    const version = receipts.map((receipt: { id: string }) => receipt.id).join(":");
    if (version !== receiptVersion) {
      receiptVersion = version;
      void drawer?.updateContext();
      window.dispatchEvent(new CustomEvent("agent-results-received", { detail: { sampleId: assistantPage.value.sampleId } }));
    }
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function start() {
  if (drawer || starting || !mount.value || !user.isAuthenticated) return;
  starting = true;
  error.value = "";
  try {
    config = await request("/assistant/config?origin=" + encodeURIComponent(location.origin));
    if (stopped || !user.isAuthenticated) return;
    if (!(window as any).AssistantDrawer)
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = config.agentUrl + "/static/assistant-embed.js";
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("Could not load the assistant."));
        document.head.appendChild(script);
      });
    if (stopped || !user.isAuthenticated) return;
    enabled.value = true;
    drawer = (window as any).AssistantDrawer.mount({
      target: mount.value,
      src: config.agentUrl + "/assistant",
      siteId: config.siteId,
      title: "MSCAN assistant",
      getAuthorization: () => request("/assistant/bootstrap", { origin: location.origin }),
      getToken: async () => (await request("/assistant/ticket", { origin: location.origin })).token,
      onEvent: (event: any) => {
        if (event.session_id) sessionId.value = event.session_id;
        if (["run-complete", "website-connected"].includes(event.type)) void refreshResults();
        if (event.type === "website-error") error.value = event.message;
      },
      adapter: {
        getPageContext: snapshot,
        listResources: async ({ sample_id = "", offset = 0, limit = 50 }: any) =>
          request(
            "/assistant/resources?sampleId=" +
              encodeURIComponent(sample_id || assistantPage.value.sampleId || "") +
              "&offset=" +
              offset +
              "&limit=" +
              limit
          ),
        importResource: async ({ resource_id }: any) => {
          const file = await request("/assistant/import-resource", { resource_id, session_id: sessionId.value });
          drawer?.refreshFiles?.();
          return { resource_id, file };
        },
        readTable: table,
        readFigure: async ({ resource_id }: any) => {
          if (resource_id !== "qc_chart") throw new Error("Unknown figure.");
          const data = await table({ resource_id: "qc_summary" });
          return {
            resource_id,
            title: "QC retention",
            description: "Read counts at each processing stage",
            x_axis: { label: "Stage" },
            y_axis: { label: "Reads", unit: "reads" },
            series: [{ name: "Reads", values: data.rows.map(r => r.reads) }],
            source_table: "qc_summary"
          };
        },
        exportData: async ({ resource_id }: any) => {
          const all = await table({ resource_id, limit: 200 });
          const rows = [...all.rows];
          for (let offset = 200; offset < all.total_rows; offset += 200)
            rows.push(...(await table({ resource_id, offset, limit: 200 })).rows);
          const quote = (v: unknown) =>
            '"' + String(v == null ? "" : typeof v === "object" ? JSON.stringify(v) : v).replaceAll('"', '""') + '"';
          return {
            filename: "mscan_" + resource_id + ".csv",
            content_type: "text/csv",
            content:
              [
                all.columns.map(c => quote(c.name)).join(","),
                ...rows.map(row => all.columns.map(c => quote(row[c.name])).join(","))
              ].join("\n") + "\n"
          };
        },
        searchManual: () => ({ version: "1", sections: [{ id: manual.section_id, title: manual.title, excerpt: manual.text }] }),
        readManual: ({ section_id }: any) => {
          if (section_id !== manual.section_id) throw new Error("Unknown guide section.");
          return manual;
        },
        navigate: async ({ route_id }: any) => {
          const path = route_id === "home" ? "/" : route_id === "samples" ? "/sample/metagenomic" : null;
          if (!path) throw new Error("Unknown route.");
          await router.push(path);
          return { route_id, message: "Opened " + path };
        }
      }
    });
    timer = setInterval(() => {
      if (assistantPage.value.sampleId) void refreshResults();
    }, 5000);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    starting = false;
  }
}
watch(
  () => user.isAuthenticated,
  value => {
    if (value) void start();
    else {
      drawer?.destroy();
      drawer = null;
      enabled.value = false;
      sessionId.value = "";
      if (timer) clearInterval(timer);
    }
  }
);
watch(
  () => router.currentRoute.value.fullPath,
  async () => {
    await nextTick();
    try {
      await drawer?.updateContext(undefined, { waitForSync: true });
    } catch (e) {
      error.value = "Page synchronization failed: " + (e as Error).message;
    }
  }
);
watch(assistantPage, () => {
  void drawer?.updateContext();
});
onMounted(() => void start());
onBeforeUnmount(() => {
  stopped = true;
  stopLogout();
  drawer?.destroy();
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div ref="mount"></div>
  <button v-if="user.isAuthenticated && !enabled && error" class="assistant-retry" :title="error" @click="start">
    Connect assistant · Retry
  </button>
</template>

<style scoped>
.assistant-retry {
  position: fixed;
  left: 20px;
  bottom: 20px;
  z-index: 2000;
  padding: 10px 16px;
  border: 1px solid #15776e;
  border-radius: 20px;
  background: white;
  color: #15695f;
  cursor: pointer;
}
</style>
