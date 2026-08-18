<script setup lang="ts">
import {
  NButton,
  NCard,
  NCheckbox,
  NEmpty,
  NInput,
  NSelect,
  NSkeleton,
  NSpace,
  NTag,
  useMessage,
} from "naive-ui";
import { computed, reactive, ref } from "vue";
import { api } from "../api";
import type { WorkItem } from "../api/types";
import WorkCard from "../components/WorkCard.vue";
import { QUALITY_OPTIONS } from "../shared/quality";
import { useJobsStore } from "../stores/jobs";

const message = useMessage();
const jobs = useJobsStore();

const url = ref("");
const quality = ref("");
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
  const target = url.value.trim();
  if (!target) {
    message.warning("请输入主页 / 合集 / 音乐链接");
    return;
  }
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

async function downloadSelected() {
  const urls = state.items.filter((i) => state.selected.has(i.aweme_id)).map((i) => i.download_url);
  if (!urls.length) return;
  submitting.value = true;
  try {
    await api.downloadBatch(urls, quality.value || undefined);
    message.success(`已提交 ${urls.length} 个下载任务`);
    state.selected = new Set();
    void jobs.refresh();
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  } finally {
    submitting.value = false;
  }
}

async function downloadOne(item: WorkItem, tier?: string) {
  try {
    await api.download(item.download_url, tier ?? (quality.value || undefined));
    message.success(tier ? `已提交下载（${tier}）` : "已提交下载任务");
    void jobs.refresh();
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  }
}

const SOURCE_LABEL: Record<string, string> = {
  user: "用户主页",
  mix: "合集",
  music: "音乐",
};
</script>

<template>
  <n-card title="作品浏览（按需下载）">
    <n-space vertical size="large">
      <n-space align="center" :wrap="false">
        <n-input
          v-model:value="url"
          placeholder="粘贴主页 / 合集 / 音乐链接，获取作品列表后按需勾选下载"
          style="min-width: 320px; flex: 1"
          @keydown.enter="fetchList(true)"
        />
        <n-button type="primary" :loading="loading" @click="fetchList(true)">获取列表</n-button>
      </n-space>

      <n-empty v-if="error" :description="error">
        <template #extra>
          <n-button size="small" @click="fetchList(true)">重试</n-button>
        </template>
      </n-empty>

      <template v-if="state.items.length">
        <n-space align="center">
          <n-checkbox :checked="allSelected" @update:checked="toggleAll">全选</n-checkbox>
          <span style="font-size: 13px; color: var(--dd-text-secondary)">
            已选 {{ state.selected.size }} / {{ state.items.length }}
          </span>
          <n-tag v-if="state.sourceType" size="small" round>
            {{ SOURCE_LABEL[state.sourceType] ?? state.sourceType }}
          </n-tag>
          <span style="flex: 1"></span>
          <span style="font-size: 12px; color: var(--dd-text-secondary)">批量画质</span>
          <n-select
            v-model:value="quality"
            :options="QUALITY_OPTIONS"
            size="small"
            style="width: 180px"
          />
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
        <n-skeleton v-for="i in 8" :key="i" height="180px" :sharp="false" />
      </div>

      <n-empty
        v-else-if="!error && state.fetchedUrl"
        description="未获取到作品，请检查链接或登录状态"
      />
    </n-space>
  </n-card>
</template>

<style scoped>
.works-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: var(--dd-space-4);
}
@media (max-width: 480px) {
  .works-grid {
    grid-template-columns: 1fr;
  }
}
</style>
