<script setup lang="ts">
import {
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NDrawer,
  NDrawerContent,
  NPopconfirm,
  NRadioButton,
  NRadioGroup,
  NSpace,
  NTag,
  useMessage,
} from "naive-ui";
import { computed, ref } from "vue";
import type { JobDto } from "../api/types";
import JobList from "../components/JobList.vue";
import { formatAbsoluteTime, formatBytes } from "../shared/format";
import { useJobsStore } from "../stores/jobs";

const jobs = useJobsStore();
const message = useMessage();

type Filter = "all" | "active" | "success" | "failed" | "cancelled";
const filter = ref<Filter>("all");

const filtered = computed(() => {
  const list = jobs.sorted;
  switch (filter.value) {
    case "active":
      return list.filter((j) => j.status === "pending" || j.status === "running");
    case "success":
      return list.filter((j) => j.status === "success");
    case "failed":
      return list.filter((j) => j.status === "failed" || j.status === "partial");
    case "cancelled":
      return list.filter((j) => j.status === "cancelled");
    default:
      return list;
  }
});

const failedCount = computed(
  () => jobs.jobs.filter((j) => j.status === "failed" || j.status === "partial").length,
);

const selected = ref<JobDto | null>(null);
// 抽屉打开期间跟随 SSE 快照实时刷新
const selectedLive = computed(() =>
  selected.value ? (jobs.jobs.find((j) => j.job_id === selected.value?.job_id) ?? null) : null,
);

async function clearFinished() {
  try {
    const deleted = await jobs.clearFinished();
    message.success(`已清除 ${deleted} 条已结束任务`);
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  }
}
</script>

<template>
  <n-card title="任务中心">
    <template #header-extra>
      <n-space align="center">
        <n-radio-group v-model:value="filter" size="small">
          <n-radio-button value="all">全部（{{ jobs.jobs.length }}）</n-radio-button>
          <n-radio-button value="active">进行中（{{ jobs.activeCount }}）</n-radio-button>
          <n-radio-button value="success">成功</n-radio-button>
          <n-radio-button value="failed">失败（{{ failedCount }}）</n-radio-button>
          <n-radio-button value="cancelled">已取消</n-radio-button>
        </n-radio-group>
        <n-popconfirm @positive-click="clearFinished">
          <template #trigger>
            <n-button size="small" quaternary type="error">清空已结束</n-button>
          </template>
          清除全部已结束任务记录？（不影响已下载文件）
        </n-popconfirm>
      </n-space>
    </template>
    <JobList :jobs="filtered" @select="selected = $event" />

    <n-drawer
      :show="selected !== null"
      :width="480"
      placement="right"
      @update:show="if (!$event) selected = null;"
    >
      <n-drawer-content v-if="selectedLive" title="任务详情" closable>
        <n-descriptions :column="1" label-placement="left" size="small">
          <n-descriptions-item label="任务 ID">{{ selectedLive.job_id }}</n-descriptions-item>
          <n-descriptions-item label="链接">
            <a :href="selectedLive.url" target="_blank" rel="noreferrer">{{ selectedLive.url }}</a>
          </n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag size="small">{{ selectedLive.status }}</n-tag>
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.options?.video_quality" label="画质">
            {{ selectedLive.options.video_quality }}
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">
            {{ formatAbsoluteTime(selectedLive.created_at) }}
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.started_at" label="开始时间">
            {{ formatAbsoluteTime(selectedLive.started_at) }}
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.finished_at" label="结束时间">
            {{ formatAbsoluteTime(selectedLive.finished_at) }}
          </n-descriptions-item>
          <n-descriptions-item label="条目统计">
            共 {{ selectedLive.total }} / 成功 {{ selectedLive.success }} / 失败
            {{ selectedLive.failed }} / 跳过 {{ selectedLive.skipped }}
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.progress.author" label="作者">
            {{ selectedLive.progress.author }}
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.progress.output_dir" label="输出目录">
            {{ selectedLive.progress.output_dir }}
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.status === 'running'" label="当前进度">
            {{ selectedLive.progress.items_done }}/{{ selectedLive.progress.items_total }} 条
            <template v-if="selectedLive.progress.current">
              · {{ formatBytes(selectedLive.progress.current.bytes_read) }} /
              {{ formatBytes(selectedLive.progress.current.bytes_total) }}
            </template>
          </n-descriptions-item>
          <n-descriptions-item v-if="selectedLive.error" label="错误">
            <span style="color: #d03050; word-break: break-all">{{ selectedLive.error }}</span>
          </n-descriptions-item>
        </n-descriptions>
      </n-drawer-content>
    </n-drawer>
  </n-card>
</template>
