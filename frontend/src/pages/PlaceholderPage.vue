<script setup lang="ts">
import { NCard, NEmpty } from "naive-ui";
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => (route.meta.title as string) || "");
const stage = computed(() => (route.meta.stage as string) || "");
</script>

<template>
  <n-card :title="title">
    <n-empty
      :description="`「${title}」规划中（${stage} 阶段交付），详见 dev_docs/webui-redesign-report.md`"
    />
  </n-card>
</template>
