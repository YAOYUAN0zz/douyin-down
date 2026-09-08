<script setup lang="ts">
/** 作品列表面板：按链接拉取作品并按需勾选下载。
 *
 * 链接输入与画质选择由下载页统一持有（单一来源），本组件只负责列表本身。
 */
import { NButton, NCheckbox, NEmpty, NSkeleton, NSpace, NTag } from "naive-ui";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { api } from "../api";
import type { WorkItem } from "../api/types";
import WorkCard from "./WorkCard.vue";
import { useJobsStore } from "../stores/jobs";

const BATCH_SIZE = 100;

type LoadKind = "initial" | "manual" | "auto";
type LoadResult = "loaded" | "cancelled" | "failed" | "blocked";

const props = defineProps<{
  /** 要浏览的链接；变更即重新拉取，空串表示收起面板 */
  url: string;
  /** 批量下载画质；空表示跟随全局配置 */
  quality: string;
}>();

const emit = defineEmits<{
  /** 提交下载后通知父级（用于提示与任务刷新） */
  submitted: [count: number];
  error: [message: string];
}>();

const jobs = useJobsStore();

const loading = ref(false);
const loadingMore = ref(false);
const loadingAll = ref(false);
const submitting = ref(false);
const initialError = ref("");
const appendError = ref("");
const failedCursor = ref<number | null>(null);
const failedAutoLoad = ref(false);
const paginationStatus = ref<"more_available" | "complete" | "restricted">("complete");
const paginationReason = ref<"cursor_stalled" | "upstream_ended_early" | null>(null);
const reportedTotal = ref<number | null>(null);
const activeController = ref<AbortController | null>(null);

let sessionId = 0;
let autoRunId = 0;
let seenCursors = new Set<number>();

const state = reactive({
  items: [] as WorkItem[],
  sourceType: "",
  cursor: 0,
  hasMore: false,
  fetchedUrl: "",
  selected: new Set<string>(),
  loadedPages: 0,
});

function isAbortError(err: unknown): boolean {
  return (err as Error).name === "AbortError";
}

function cancelActiveRequest() {
  activeController.value?.abort();
  activeController.value = null;
}

function resetState(target: string) {
  state.items = [];
  state.sourceType = "";
  state.cursor = 0;
  state.hasMore = false;
  state.fetchedUrl = target;
  state.selected = new Set();
  state.loadedPages = 0;
  seenCursors = new Set([0]);
  initialError.value = "";
  appendError.value = "";
  failedCursor.value = null;
  failedAutoLoad.value = false;
  paginationStatus.value = "complete";
  paginationReason.value = null;
  reportedTotal.value = null;
}

function setLoading(kind: LoadKind, value: boolean) {
  if (kind === "initial") loading.value = value;
  else if (kind === "manual") loadingMore.value = value;
  else loadingAll.value = value;
}

function isCurrentRequest(
  requestSession: number,
  target: string,
  controller: AbortController,
  requestAutoRun?: number,
): boolean {
  return (
    sessionId === requestSession &&
    props.url.trim() === target &&
    activeController.value === controller &&
    !controller.signal.aborted &&
    (requestAutoRun === undefined || autoRunId === requestAutoRun)
  );
}

/** 加载一页，所有入口统一走这里，避免分页状态与去重逻辑分叉。 */
async function loadPage(
  target: string,
  cursor: number,
  kind: LoadKind,
  requestAutoRun?: number,
): Promise<LoadResult> {
  if (activeController.value) return "cancelled";

  const controller = new AbortController();
  const requestSession = sessionId;
  activeController.value = controller;
  setLoading(kind, true);
  if (kind === "initial") initialError.value = "";
  else appendError.value = "";

  try {
    const page = await api.worksList(target, cursor, 20, controller.signal);
    if (!isCurrentRequest(requestSession, target, controller, requestAutoRun)) return "cancelled";

    const known = new Set(state.items.map((item) => item.aweme_id));
    // 增量 append：不整表重建，避免闪烁与封面重复请求。
    state.items.push(...page.items.filter((item) => !known.has(item.aweme_id)));
    state.sourceType = page.source_type;
    state.cursor = page.cursor;
    state.hasMore = page.has_more;
    state.loadedPages += 1;
    failedCursor.value = null;
    failedAutoLoad.value = false;
    paginationStatus.value = page.pagination_status;
    paginationReason.value = page.pagination_reason;
    reportedTotal.value = page.reported_total;

    if (page.pagination_status === "restricted") {
      state.hasMore = false;
      return "blocked";
    }
    if (page.has_more) {
      // cursor 是上游不透明值，不要求单调；重复才视为异常循环。
      if (page.cursor === cursor || seenCursors.has(page.cursor)) {
        state.hasMore = false;
        paginationStatus.value = "restricted";
        paginationReason.value = "cursor_stalled";
        return "blocked";
      }
      seenCursors.add(page.cursor);
    }
    return "loaded";
  } catch (err) {
    if (
      !isCurrentRequest(requestSession, target, controller, requestAutoRun) ||
      isAbortError(err)
    ) {
      return "cancelled";
    }

    const message = (err as Error).message;
    if (!state.items.length && kind === "initial") {
      initialError.value = message;
    } else {
      appendError.value = message;
      failedCursor.value = cursor;
      failedAutoLoad.value = kind === "auto";
    }
    return "failed";
  } finally {
    if (activeController.value === controller) {
      activeController.value = null;
      // 自动加载由 loadAll() 覆盖整个循环的加载态，不能在每一页间闪断。
      if (kind !== "auto") setLoading(kind, false);
    }
  }
}

async function startSession(target: string) {
  cancelActiveRequest();
  sessionId += 1;
  autoRunId += 1;
  loading.value = false;
  loadingMore.value = false;
  loadingAll.value = false;
  resetState(target);
  await loadPage(target, 0, "initial");
}

async function loadMore(cursor = state.cursor) {
  if (!state.hasMore || loadingMore.value || loadingAll.value || loading.value) return;
  await loadPage(state.fetchedUrl, cursor, "manual");
}

async function loadAll() {
  if (!state.hasMore || loadingMore.value || loadingAll.value || loading.value) return;

  const target = state.fetchedUrl;
  const requestSession = sessionId;
  const requestAutoRun = ++autoRunId;
  loadingAll.value = true;
  appendError.value = "";

  try {
    while (
      sessionId === requestSession &&
      autoRunId === requestAutoRun &&
      state.hasMore &&
      !activeController.value
    ) {
      const result = await loadPage(target, state.cursor, "auto", requestAutoRun);
      if (result !== "loaded") break;
    }
  } finally {
    if (sessionId === requestSession && autoRunId === requestAutoRun) loadingAll.value = false;
  }
}

function stopLoadingAll() {
  autoRunId += 1;
  cancelActiveRequest();
  loadingAll.value = false;
}

function retryInitial() {
  void startSession(props.url.trim());
}

function retryAppend() {
  if (failedCursor.value === null) return;
  if (failedAutoLoad.value) void loadAll();
  else void loadMore(failedCursor.value);
}

watch(
  () => props.url,
  (url) => {
    const target = url.trim();
    if (target) void startSession(target);
    else {
      cancelActiveRequest();
      sessionId += 1;
      autoRunId += 1;
      loadingAll.value = false;
      resetState("");
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  sessionId += 1;
  autoRunId += 1;
  cancelActiveRequest();
});

function toggle(id: string) {
  if (state.selected.has(id)) state.selected.delete(id);
  else state.selected.add(id);
}

const allSelected = computed(
  () => state.items.length > 0 && state.selected.size === state.items.length,
);
const selectionLabel = computed(() => `已选 ${state.selected.size} / ${state.items.length}`);
const loadAllProgressLabel = computed(
  () => `正在加载全部作品：已加载 ${state.items.length} 条，已完成 ${state.loadedPages} 页`,
);
const paginationNotice = computed(() => {
  if (paginationStatus.value !== "restricted") return "";
  const totalHint = reportedTotal.value ? `，作者资料显示约 ${reportedTotal.value} 条` : "";
  if (paginationReason.value === "cursor_stalled") {
    return `上游未返回可用的下一页游标，当前仅获取 ${state.items.length} 条${totalHint}，无法确认是否完整`;
  }
  return `上游在满页后提前结束，当前仅获取 ${state.items.length} 条${totalHint}，无法确认是否完整`;
});

function toggleAll(checked: boolean) {
  state.selected = checked ? new Set(state.items.map((item) => item.aweme_id)) : new Set();
}

const undownloadedCount = computed(() => state.items.filter((item) => !item.downloaded).length);

/** 只勾选历史库里没有的作品，避免重复下载 */
function selectUndownloaded() {
  state.selected = new Set(
    state.items.filter((item) => !item.downloaded).map((item) => item.aweme_id),
  );
}

function batch<T>(items: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < items.length; index += size)
    result.push(items.slice(index, index + size));
  return result;
}

async function downloadSelected() {
  const selectedItems = state.items.filter((item) => state.selected.has(item.aweme_id));
  if (!selectedItems.length) return;

  submitting.value = true;
  let submitted = 0;
  try {
    for (const items of batch(selectedItems, BATCH_SIZE)) {
      await api.downloadBatch(
        items.map((item) => item.download_url),
        props.quality || undefined,
      );
      submitted += items.length;
      // 成功批次立即取消勾选；失败时剩余作品还可直接重试。
      for (const item of items) state.selected.delete(item.aweme_id);
    }
    emit("submitted", submitted);
    void jobs.refresh();
  } catch (err) {
    if (submitted) {
      emit("submitted", submitted);
      void jobs.refresh();
    }
    emit("error", `已提交 ${submitted}/${selectedItems.length} 个任务：${(err as Error).message}`);
  } finally {
    submitting.value = false;
  }
}

async function downloadOne(item: WorkItem, tier?: string) {
  try {
    await api.download(item.download_url, tier ?? (props.quality || undefined));
    emit("submitted", 1);
    void jobs.refresh();
  } catch (err) {
    emit("error", (err as Error).message);
  }
}

const SOURCE_LABEL: Record<string, string> = {
  user: "用户主页",
  mix: "合集",
  music: "音乐",
  video: "单个作品",
};
</script>

<template>
  <n-space vertical size="large" class="works-panel">
    <n-empty v-if="initialError && !state.items.length" :description="initialError">
      <template #extra>
        <n-button size="small" @click="retryInitial">重试</n-button>
      </template>
    </n-empty>

    <template v-else-if="state.items.length">
      <n-space align="center">
        <n-checkbox :checked="allSelected" @update:checked="toggleAll">全选</n-checkbox>
        <n-button
          size="tiny"
          quaternary
          :disabled="!undownloadedCount"
          title="只勾选历史记录里没有的作品"
          @click="selectUndownloaded"
        >
          仅选未下载（{{ undownloadedCount }}）
        </n-button>
        <span class="selection-status">{{ selectionLabel }}</span>
        <n-tag v-if="state.sourceType" size="small" round>
          {{ SOURCE_LABEL[state.sourceType] ?? state.sourceType }}
        </n-tag>
        <n-button
          v-if="state.hasMore && !loadingAll"
          size="small"
          type="primary"
          :disabled="loading || loadingMore"
          @click="loadAll"
        >
          查看全部作品
        </n-button>
        <span class="toolbar-spacer"></span>
        <n-button
          type="primary"
          size="small"
          :disabled="!state.selected.size"
          :loading="submitting"
          @click="downloadSelected"
        >
          下载选中（{{ state.selected.size }}）
        </n-button>
      </n-space>

      <div class="works-grid">
        <WorkCard
          v-for="item in state.items"
          :key="item.aweme_id"
          :item="item"
          :selected="state.selected.has(item.aweme_id)"
          @toggle="toggle(item.aweme_id)"
          @download="(tier) => downloadOne(item, tier)"
        />
      </div>

      <n-space v-if="loadingAll" vertical align="center" class="load-all-status">
        <span>{{ loadAllProgressLabel }}</span>
        <n-button size="small" @click="stopLoadingAll">停止加载</n-button>
      </n-space>

      <n-space v-else-if="appendError" vertical align="center" class="append-error">
        <span>{{ appendError }}</span>
        <n-button v-if="failedCursor !== null" size="small" @click="retryAppend">
          {{ failedAutoLoad ? "重试并继续查看全部" : "重试本页" }}
        </n-button>
      </n-space>

      <p v-else-if="paginationNotice" class="pagination-notice">{{ paginationNotice }}</p>

      <n-space v-else-if="state.hasMore" justify="center">
        <n-button :loading="loadingMore" :disabled="loadingMore" @click="loadMore()">
          加载更多
        </n-button>
      </n-space>

      <p v-else-if="state.loadedPages > 1" class="load-complete">
        已加载全部作品：{{ state.items.length }} 条，共 {{ state.loadedPages }} 页
      </p>
    </template>

    <div v-else-if="loading" class="works-grid">
      <n-skeleton v-for="i in 8" :key="i" height="300px" :sharp="false" />
    </div>

    <n-empty v-else description="未获取到作品，请检查链接或登录状态" />
  </n-space>
</template>

<style scoped>
.works-panel {
  container: works-panel / inline-size;
  min-width: 0;
}
.works-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: var(--dd-space-4);
}
.selection-status,
.load-all-status,
.append-error,
.pagination-notice,
.load-complete {
  color: var(--dd-text-secondary);
  font-size: 13px;
}
.toolbar-spacer {
  flex: 1;
}
.pagination-notice,
.load-complete {
  margin: 0;
  text-align: center;
}
.pagination-notice {
  color: #d97706;
}
</style>
