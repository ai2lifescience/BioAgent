import { ref, shallowRef, watch, onBeforeUnmount } from "vue";

export type AssistantPageSnapshot = {
  sampleId?: string;
  sampleName?: string;
  projectId?: string;
  dataType?: string;
  program?: string;
  rows?: Record<string, unknown>[];
  filters?: Record<string, unknown>;
};
export const assistantPage = shallowRef<AssistantPageSnapshot>({});

/** One explicit hook in a host page; no cross-origin DOM inspection. */
export function registerAssistantContext(read: () => AssistantPageSnapshot) {
  let owned: AssistantPageSnapshot;
  watch(
    read,
    value => {
      owned = JSON.parse(JSON.stringify(value));
      assistantPage.value = owned;
    },
    { deep: true, immediate: true }
  );
  onBeforeUnmount(() => {
    if (assistantPage.value === owned) assistantPage.value = {};
  });
}

/** Refresh native result components when a backend delivery changes this sample. */
export function useReceivedResults(sample: () => string) {
  const version = ref(0);
  const receive = (event: Event) => {
    if ((event as CustomEvent).detail?.sampleId === sample()) version.value++;
  };
  window.addEventListener("agent-results-received", receive);
  onBeforeUnmount(() => window.removeEventListener("agent-results-received", receive));
  return version;
}
