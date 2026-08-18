<script setup lang="ts">
import { NButton, NCard, NInput, NSelect, NSpace, NTag, useMessage } from "naive-ui";
import { computed, ref } from "vue";
import { api } from "../api";
import JobList from "../components/JobList.vue";
import { extractUrls } from "../shared/format";
import { QUALITY_OPTIONS } from "../shared/quality";
import { useJobsStore } from "../stores/jobs";

const message = useMessage();
const jobs = useJobsStore();

const input = ref("");
const quality = ref("");
const submitting = ref(false);

const urls = computed(() => extractUrls(input.value));

async function submit() {
  const list = urls.value;
  if (!list.length) {
    message.warning("请粘贴至少一条抖音链接");
    return;
  }
  submitting.value = true;
  try {
    if (list.length === 1) {
      await api.download(list[0] ?? "", quality.value || undefined);
    } else {
      await api.downloadBatch(list, quality.value || undefined);
    }
    message.success(`已提交 ${list.length} 个下载任务`);
    input.value = "";
    void jobs.refresh();
  } catch (err) {
    message.error((err as Error).message, { duration: 8000, closable: true });
  } finally {
    submitting.value = false;
  }
}

const recentJobs = computed(() => jobs.sorted.slice(0, 5));
</script>

<template>
  <n-space vertical size="large">
    <n-card title="快速下载">
      <n-space vertical>
        <n-input
          v-model:value="input"
          type="textarea"
          :rows="4"
          placeholder="粘贴抖音链接，支持一次多条（换行或空格分隔）：视频 / 图文 / 合集 / 音乐 / 主页 / 短链"
          @keydown.ctrl.enter="submit"
        />
        <n-space align="center">
          <n-tag v-if="urls.length" size="small" type="info">识别到 {{ urls.length }} 条链接</n-tag>
          <span style="color: var(--dd-text-secondary); font-size: 13px">画质</span>
          <n-select
            v-model:value="quality"
            :options="QUALITY_OPTIONS"
            style="width: 220px"
            size="small"
          />
          <n-button type="primary" :loading="submitting" :disabled="!urls.length" @click="submit">
            开始下载{{ urls.length > 1 ? `（${urls.length} 条）` : "" }}
          </n-button>
          <span style="color: var(--dd-text-secondary); font-size: 12px">Ctrl+Enter 提交</span>
        </n-space>
      </n-space>
    </n-card>

    <n-card title="最近任务">
      <template #header-extra>
        <router-link to="/jobs" style="font-size: 13px">查看全部 →</router-link>
      </template>
      <JobList :jobs="recentJobs" compact />
    </n-card>
  </n-space>
</template>
