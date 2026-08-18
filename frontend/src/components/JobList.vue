<script setup lang="ts">
import { NEmpty, NProgress, NSpin, NTag, NTooltip } from "naive-ui";
import type { JobDto } from "../api/types";
import { formatAbsoluteTime, formatBytes, formatRelativeTime } from "../shared/format";
import { useJobsStore } from "../stores/jobs";

defineProps<{
  jobs: JobDto[];
  compact?: boolean;
}>();

const store = useJobsStore();

const STATUS_META: Record<
  string,
  { text: string; type: "default" | "info" | "success" | "error" }
> = {
  pending: { text: "排队中", type: "default" },
  running: { text: "下载中", type: "info" },
  success: { text: "完成", type: "success" },
  failed: { text: "失败", type: "error" },
};

function statusMeta(status: string) {
  return STATUS_META[status] ?? { text: status, type: "default" as const };
}

function bytePercent(job: JobDto): number | null {
  const cur = job.progress.current;
  if (!cur || !cur.bytes_total) return null;
  return Math.min(100, Math.round((cur.bytes_read / cur.bytes_total) * 100));
}

function progressText(job: JobDto): string {
  const p = job.progress;
  const parts: string[] = [];
  if (p.items_total > 0) parts.push(`${p.items_done}/${p.items_total} 条`);
  const stepLine = [p.author, p.step, p.detail].filter(Boolean).join(" · ");
  if (stepLine) parts.push(stepLine);
  return parts.join("　");
}

function resultText(job: JobDto): string {
  const parts = [`成功 ${job.success}`];
  if (job.failed) parts.push(`失败 ${job.failed}`);
  if (job.skipped) parts.push(`跳过 ${job.skipped}`);
  return parts.join(" / ");
}

async function copyOutputDir(path: string) {
  await navigator.clipboard.writeText(path);
}
</script>

<template>
  <n-spin :show="store.loading">
    <n-empty v-if="!jobs.length && !store.loading" description="暂无任务" />
    <div v-else class="job-list">
      <div v-for="job in jobs" :key="job.job_id" class="job-row">
        <div class="job-row-main">
          <a :href="job.url" target="_blank" rel="noreferrer" class="job-url">{{ job.url }}</a>
          <n-tag v-if="job.options?.video_quality" size="tiny" round>
            {{ job.options.video_quality }}
          </n-tag>
          <n-tag size="small" round :type="statusMeta(job.status).type">
            {{ statusMeta(job.status).text }}
          </n-tag>
          <span class="job-time" :title="formatAbsoluteTime(job.created_at)">
            {{ formatRelativeTime(job.created_at) }}
          </span>
        </div>

        <div v-if="job.status === 'running'" class="job-progress">
          <span class="job-progress-text">{{ progressText(job) }}</span>
          <n-progress
            v-if="bytePercent(job) !== null"
            type="line"
            :percentage="bytePercent(job) ?? 0"
            :height="6"
            :show-indicator="false"
          />
          <span v-if="job.progress.current" class="job-progress-bytes">
            {{ formatBytes(job.progress.current.bytes_read) }} /
            {{ formatBytes(job.progress.current.bytes_total) }}
          </span>
        </div>

        <div v-else-if="job.status !== 'pending'" class="job-result">
          <span>{{ resultText(job) }}</span>
          <n-tooltip v-if="job.progress.output_dir" trigger="hover">
            <template #trigger>
              <span class="job-output-dir" @click="copyOutputDir(job.progress.output_dir ?? '')">
                📁 {{ job.progress.output_dir }}
              </span>
            </template>
            点击复制输出目录
          </n-tooltip>
          <span v-if="job.error" class="job-error" :title="job.error">{{ job.error }}</span>
        </div>
      </div>
    </div>
  </n-spin>
</template>

<style scoped>
.job-list {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-3);
}
.job-row {
  border: 1px solid var(--dd-border);
  border-radius: var(--dd-radius);
  padding: var(--dd-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
}
.job-row-main {
  display: flex;
  align-items: center;
  gap: var(--dd-space-2);
  flex-wrap: wrap;
}
.job-url {
  color: inherit;
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.job-time {
  margin-left: auto;
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.job-progress {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-1);
}
.job-progress-text,
.job-progress-bytes {
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.job-result {
  display: flex;
  gap: var(--dd-space-3);
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
}
.job-output-dir {
  color: var(--dd-text-secondary);
  cursor: pointer;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-error {
  color: #d03050;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
