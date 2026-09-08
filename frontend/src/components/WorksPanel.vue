<script setup lang="ts">
/** 作品列表面板：按链接拉取作品并按需勾选下载。
 *
 * 链接输入与画质选择由下载页统一持有（单一来源），本组件只负责列表本身。
 */
import { NButton, NCheckbox, NEmpty, NSkeleton, NSpace, NTag } from "naive-ui";
import { computed, reactive, ref, watch } from "vue";
import { api } from "../api";
import type { WorkItem } from "../api/types";
import WorkCard from "./WorkCard.vue";
import { useJobsStore } from "../stores/jobs";

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
const submitting = ref(false);
const error = ref("");

const state = reactive({
  items: [] as WorkItem[],
  sourceType: "",
  cursor: 0,
  hasMore: false,
  fetchedUrl: "",
  selected: new Set<string>(),
});

async function fetchList(reset: boolean) {
  const target = props.url.trim();
  if (!target) return;
  const isReset = reset || target !== state.fetchedUrl;
  if (isReset) {
    loading.value = true;
  } else {
    loadingMore.value = true;
  }
  error.value = "";
  try {
    const page = await api.worksList(target, isReset ? 0 : state.cursor);
    if (isReset) {
      state.items = [];
      state.selected = new Set();
      state.fetchedUrl = target;
    }
    const known = new Set(state.items.map((i) => i.aweme_id));
    // 增量 append：不整表重建，避免闪烁与封面重复请求
    state.items.push(...page.items.filter((i) => !known.has(i.aweme_id)));
    state.sourceType = page.source_type;
    state.cursor = page.cursor;
    state.hasMore = page.has_more;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

watch(
  () => props.url,
  (url) => {
    if (url.trim()) void fetchList(true);
  },
  { immediate: true },
);

function toggle(id: string) {
  if (state.selected.has(id)) state.selected.delete(id);
  else state.selected.add(id);
}

const allSelected = computed(
  () => state.items.length > 0 && state.selected.size === state.items.length,
);

function toggleAll(checked: boolean) {
  state.selected = checked ? new Set(state.items.map((i) => i.aweme_id)) : new Set();
}

const undownloadedCount = computed(() => state.items.filter((i) => !i.downloaded).length);

/** 只勾选历史库里没有的作品，避免重复下载 */
function selectUndownloaded() {
  state.selected = new Set(state.items.filter((i) => !i.downloaded).map((i) => i.aweme_id));
}

async function downloadSelected() {
  const urls = state.items.filter((i) => state.selected.has(i.aweme_id)).map((i) => i.download_url);
  if (!urls.length) return;
  submitting.value = true;
  try {
    await api.downloadBatch(urls, props.quality || undefined);
    state.selected = new Set();
    emit("submitted", urls.length);
    void jobs.refresh();
  } catch (err) {
    emit("error", (err as Error).message);
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
    <n-empty v-if="error" :description="error">
      <template #extra>
        <n-button size="small" @click="fetchList(true)">重试</n-button>
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
        <span style="font-size: 13px; color: var(--dd-text-secondary)">
          已选 {{ state.selected.size }} / {{ state.items.length }}
        </span>
        <n-tag v-if="state.sourceType" size="small" round>
          {{ SOURCE_LABEL[state.sourceType] ?? state.sourceType }}
        </n-tag>
        <span style="flex: 1"></span>
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

      <n-space v-if="state.hasMore" justify="center">
        <n-button :loading="loadingMore" @click="fetchList(false)">加载更多</n-button>
      </n-space>
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
</style>
