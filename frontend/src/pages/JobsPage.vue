<script setup lang="ts">
import { NCard, NRadioButton, NRadioGroup, NSpace } from "naive-ui";
import { computed, ref } from "vue";
import JobList from "../components/JobList.vue";
import { useJobsStore } from "../stores/jobs";

const jobs = useJobsStore();

type Filter = "all" | "active" | "success" | "failed";
const filter = ref<Filter>("all");

const filtered = computed(() => {
  const list = jobs.sorted;
  switch (filter.value) {
    case "active":
      return list.filter((j) => j.status === "pending" || j.status === "running");
    case "success":
      return list.filter((j) => j.status === "success");
    case "failed":
      return list.filter((j) => j.status === "failed");
    default:
      return list;
  }
});
</script>

<template>
  <n-card title="任务中心">
    <template #header-extra>
      <n-space align="center">
        <n-radio-group v-model:value="filter" size="small">
          <n-radio-button value="all">全部（{{ jobs.jobs.length }}）</n-radio-button>
          <n-radio-button value="active">进行中（{{ jobs.activeCount }}）</n-radio-button>
          <n-radio-button value="success">成功</n-radio-button>
          <n-radio-button value="failed">失败</n-radio-button>
        </n-radio-group>
      </n-space>
    </template>
    <JobList :jobs="filtered" />
  </n-card>
</template>
