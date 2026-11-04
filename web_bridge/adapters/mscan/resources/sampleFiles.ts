import { ref, watch, onBeforeUnmount } from "vue";
import { getAccessToken } from "@/utils/authToken";

/** Files attached to a native sample result; no separate assistant results UI. */
export function useSampleFiles(sample: () => string) {
  const files = ref<{ id: string; name: string; resource_id: string }[]>([]);
  const error = ref("");
  let generation = 0;
  const prefix = ((import.meta.env.VITE_API_URL as string) || "") + "/cncb";
  async function request(path: string, body?: unknown) {
    const token = getAccessToken();
    const response = await fetch(prefix + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        ...(token ? { Authorization: "Bearer " + token } : {}),
        ...(body ? { "Content-Type": "application/json" } : {})
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const value = await response.json();
    if (!response.ok || value.code !== 200) throw new Error(value.msg || "Files unavailable");
    return value.data;
  }
  async function refresh() {
    const epoch = ++generation,
      id = sample();
    files.value = [];
    error.value = "";
    if (!id) return;
    try {
      const receipts = await request("/assistant/received?sampleId=" + encodeURIComponent(id));
      if (epoch !== generation) return;
      const seen = new Set<string>();
      files.value = receipts
        .flatMap((r: any) => r.files.map((f: any) => ({ ...f, resource_id: "result:" + r.id + ":" + f.id })))
        .filter((f: any) => {
          const key = f.resource_id;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      let offset = 0;
      while (true) {
        const page = await request("/assistant/resources?sampleId=" + encodeURIComponent(id) + "&limit=200&offset=" + offset);
        if (epoch !== generation) return;
        for (const file of page.resources) {
          if ((file.kind === "native_analysis_output" || file.kind === "native_analysis_record") && !seen.has(file.resource_id)) {
            files.value.push(file);
            seen.add(file.resource_id);
          }
        }
        offset += page.resources.length;
        if (!page.resources.length || offset >= page.total) break;
      }
    } catch (e) {
      if (epoch === generation) error.value = (e as Error).message;
    }
  }
  async function download(resource: string) {
    try {
      const ticket = await request("/assistant/received-ticket", { resource_id: resource });
      const link = document.createElement("a");
      link.href = prefix + "/assistant/received-download/" + encodeURIComponent(ticket.token);
      link.referrerPolicy = "no-referrer";
      link.click();
    } catch (e) {
      error.value = (e as Error).message;
    }
  }
  const receive = (event: Event) => {
    if ((event as CustomEvent).detail?.sampleId === sample()) void refresh();
  };
  window.addEventListener("agent-results-received", receive);
  watch(sample, refresh, { immediate: true });
  onBeforeUnmount(() => {
    generation++;
    window.removeEventListener("agent-results-received", receive);
  });
  return { files, error, download };
}
