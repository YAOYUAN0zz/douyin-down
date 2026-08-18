<script setup lang="ts">
import {
  NButton,
  NCard,
  NCode,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NPagination,
  NRadioButton,
  NRadioGroup,
  NSkeleton,
  NSpace,
  NTag,
  useMessage,
} from "naive-ui";
import { computed, onMounted, ref, watch } from "vue";
import { api } from "../api";
import type { HistoryDetail, HistoryItem, HistoryStats } from "../api/types";
import { formatUnixDate, formatUnixDateTime } from "../shared/format";
import { useJobsStore } from "../stores/jobs";

const message = useMessage();
const jobs = useJobsStore();

// 后端 aweme_type 取值（下载器写入）：video / gallery / music / live_replay
const TYPE_OPTIONS = [
  { value: "", label: "全部" },
  { value: "video", label: "视频" },
  { value: "gallery", label: "图集" },
  { value: "music", label: "音乐" },
  { value: "live_replay", label: "直播回放" },
];
const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  TYPE_OPTIONS.filter((o) => o.value).map((o) => [o.value, o.label]),
);

const query = ref("");
const author = ref("");
const awemeType = ref("");
const sort = ref<"download_time" | "create_time">("download_time");
const authorSecUid = ref("");
const page = ref(1);
const pageSize = ref(20);

const items = ref<HistoryItem[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref("");
const loaded = ref(false);

const stats = ref<HistoryStats | null>(null);
const statsWindow = ref<"7d" | "30d">("7d");
const topAuthors = computed(() =>
  statsWindow.value === "7d"
    ? (stats.value?.top_authors_7d ?? [])
    : (stats.value?.top_authors_30d ?? []),
);

const detail = ref<HistoryDetail | null>(null);
const detailLoading = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const data = await api.history({
      query: query.value.trim(),
      author: author.value.trim(),
      aweme_type: awemeType.value,
      author_sec_uid: authorSecUid.value,
      sort: sort.value,
      page: page.value,
      page_size: pageSize.value,
    });
    items.value = data.items;
    total.value = data.total;
    loaded.value = true;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

async function loadStats() {
  try {
    stats.value = await api.historyStats();
  } catch {
    // 统计是辅助信息：失败不打断列表，卡片自然显示为空
    stats.value = null;
  }
}

/** 条件变化回到第 1 页；仅翻页时保持条件 */
function reload() {
  page.value = 1;
  void load();
}

watch([awemeType, sort], reload);
watch([page, pageSize], () => void load());

onMounted(() => {
  void load();
  void loadStats();
});

function filterByAuthor(secUid: string, name: string) {
  authorSecUid.value = secUid;
  author.value = "";
  query.value = "";
  page.value = 1;
  message.info(`已筛选作者：${name}`);
  void load();
}

function clearAuthorFilter() {
  authorSecUid.value = "";
  reload();
}

/** 与后端 works 规整一致：图集走 /note/，其余走 /video/ */
function sourceUrl(item: HistoryItem): string {
  const kind = item.aweme_type === "gallery" ? "note" : "video";
  return `https://www.douyin.com/${kind}/${item.aweme_id}`;
}

/** 音乐/直播回放没有可复用的作品链接，不提供重新下载 */
function canRedownload(item: HistoryItem): boolean {
  return item.aweme_type === "video" || item.aweme_type === "gallery";
}

async function redownload(item: HistoryItem) {
  try {
    await api.download(sourceUrl(item));
    message.success("已提交下载任务（同名文件会按去重规则跳过）");
    void jobs.refresh();
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  }
}

async function copyPath(path: string | null) {
  if (!path) return;
  try {
    await navigator.clipboard.writeText(path);
    message.success("已复制输出目录");
  } catch {
    message.error(`复制失败，请手动复制：${path}`, { duration: 8000, closable: true });
  }
}

async function openDetail(item: HistoryItem) {
  detailLoading.value = true;
  detail.value = null;
  try {
    detail.value = await api.historyDetail(item.aweme_id);
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  } finally {
    detailLoading.value = false;
  }
}

const metadataText = computed(() =>
  detail.value?.metadata ? JSON.stringify(detail.value.metadata, null, 2) : "",
);
</script>

<template>
  <div class="history-layout">
    <n-card title="历史记录">
      <template #header-extra>
        <span class="muted">共 {{ total }} 条</span>
      </template>

      <n-space vertical size="large">
        <n-space align="center" :wrap="true">
          <n-input
            v-model:value="query"
            placeholder="搜索标题"
            clearable
            style="width: 220px"
            @keydown.enter="reload"
            @clear="reload"
          />
          <n-input
            v-model:value="author"
            placeholder="搜索作者"
            clearable
            style="width: 160px"
            @keydown.enter="reload"
            @clear="reload"
          />
          <n-button type="primary" size="small" :loading="loading" @click="reload">搜索</n-button>
          <n-tag v-if="authorSecUid" size="small" closable round @close="clearAuthorFilter">
            已锁定作者
          </n-tag>
          <span style="flex: 1"></span>
          <n-radio-group v-model:value="awemeType" size="small">
            <n-radio-button v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </n-radio-button>
          </n-radio-group>
          <n-radio-group v-model:value="sort" size="small">
            <n-radio-button value="download_time">按下载时间</n-radio-button>
            <n-radio-button value="create_time">按发布时间</n-radio-button>
          </n-radio-group>
        </n-space>

        <n-empty v-if="error" :description="error">
          <template #extra>
            <n-button size="small" @click="load">重试</n-button>
          </template>
        </n-empty>

        <div v-else-if="loading && !items.length" class="rows">
          <n-skeleton v-for="i in 6" :key="i" height="72px" :sharp="false" />
        </div>

        <n-empty
          v-else-if="!items.length"
          :description="loaded ? '暂无匹配的下载记录' : '加载中…'"
        />

        <div v-else class="rows">
          <div v-for="item in items" :key="item.aweme_id" class="row">
            <img
              v-if="item.cover_urls.length"
              class="row-cover"
              :src="item.cover_urls[0]"
              loading="lazy"
              referrerpolicy="no-referrer"
              alt=""
            />
            <div v-else class="row-cover row-cover-empty">无封面</div>

            <div class="row-body">
              <div class="row-title" :title="item.title || ''">
                {{ item.title || "（无标题）" }}
              </div>
              <div class="row-meta">
                <n-tag size="tiny" round>
                  {{ TYPE_LABEL[item.aweme_type] ?? item.aweme_type }}
                </n-tag>
                <span class="row-author">{{ item.author_name || "未知作者" }}</span>
                <span v-if="item.create_time">发布 {{ formatUnixDate(item.create_time) }}</span>
                <span v-if="item.download_time">
                  下载 {{ formatUnixDateTime(item.download_time) }}
                </span>
              </div>
              <div v-if="item.file_path" class="row-path" :title="item.file_path">
                {{ item.file_path }}
              </div>
            </div>

            <n-space class="row-actions" size="small" align="center">
              <n-button size="tiny" quaternary @click="copyPath(item.file_path)">复制目录</n-button>
              <n-button size="tiny" quaternary @click="openDetail(item)">元数据</n-button>
              <n-button
                size="tiny"
                quaternary
                tag="a"
                :href="sourceUrl(item)"
                target="_blank"
                rel="noreferrer"
              >
                原页面
              </n-button>
              <n-button
                v-if="canRedownload(item)"
                size="tiny"
                type="primary"
                secondary
                @click="redownload(item)"
              >
                重新下载
              </n-button>
            </n-space>
          </div>
        </div>

        <n-space v-if="total > pageSize" justify="center">
          <n-pagination
            v-model:page="page"
            v-model:page-size="pageSize"
            :item-count="total"
            :page-sizes="[20, 50, 100]"
            show-size-picker
          />
        </n-space>
      </n-space>
    </n-card>

    <n-card title="统计" class="stats-card">
      <n-space vertical size="large">
        <div>
          <div class="stat-value">{{ stats?.total ?? "—" }}</div>
          <div class="muted">累计下载作品</div>
        </div>

        <n-radio-group v-model:value="statsWindow" size="small">
          <n-radio-button value="7d">近 7 天</n-radio-button>
          <n-radio-button value="30d">近 30 天</n-radio-button>
        </n-radio-group>

        <n-empty v-if="!topAuthors.length" size="small" description="窗口内暂无下载" />
        <div v-else class="authors">
          <button
            v-for="a in topAuthors"
            :key="a.sec_uid"
            type="button"
            class="author-row"
            :title="`只看 ${a.author_name} 的记录`"
            @click="filterByAuthor(a.sec_uid, a.author_name)"
          >
            <span class="author-name">{{ a.author_name }}</span>
            <span class="muted">{{ a.download_count }}</span>
          </button>
        </div>
      </n-space>
    </n-card>

    <n-drawer
      :show="detail !== null || detailLoading"
      :width="520"
      placement="right"
      @update:show="
        if (!$event) {
          detail = null;
        }
      "
    >
      <n-drawer-content :title="detail?.title || '作品元数据'" closable>
        <n-skeleton v-if="detailLoading" text :repeat="8" />
        <template v-else-if="detail">
          <n-space vertical size="small">
            <div class="muted">作品 ID：{{ detail.aweme_id }}</div>
            <div v-if="detail.job_id" class="muted">来源任务：{{ detail.job_id }}</div>
            <div v-if="detail.file_path" class="muted">输出目录：{{ detail.file_path }}</div>
          </n-space>
          <n-code
            v-if="metadataText"
            class="metadata"
            :code="metadataText"
            language="json"
            word-wrap
          />
          <n-empty v-else description="该记录未保存元数据（或已损坏）" />
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.history-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: var(--dd-space-4);
  align-items: start;
}
@media (max-width: 900px) {
  .history-layout {
    grid-template-columns: 1fr;
  }
}

.muted {
  color: var(--dd-text-secondary);
  font-size: 12px;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
}
.row {
  display: flex;
  align-items: center;
  gap: var(--dd-space-3);
  padding: var(--dd-space-2);
  border: 1px solid var(--dd-border);
  border-radius: var(--dd-radius);
  background: var(--dd-card-bg);
}
.row-cover {
  width: 72px;
  height: 56px;
  flex-shrink: 0;
  object-fit: cover;
  border-radius: 6px;
  background: var(--dd-border);
}
.row-cover-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dd-text-secondary);
  font-size: 11px;
}
.row-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-1);
}
.row-title {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--dd-space-2);
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.row-author {
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-path {
  color: var(--dd-text-secondary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-actions {
  flex-shrink: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
}
.authors {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-1);
}
.author-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dd-space-2);
  width: 100%;
  padding: 4px 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--dd-text);
  font-size: 13px;
  cursor: pointer;
}
.author-row:hover {
  background: rgba(32, 128, 240, 0.08);
}
.author-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata {
  display: block;
  margin-top: var(--dd-space-3);
  max-height: 60vh;
  overflow: auto;
  font-size: 12px;
}
</style>
