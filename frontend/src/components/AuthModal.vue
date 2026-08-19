<script setup lang="ts">
import { NAlert, NButton, NModal, NSpace, NSpin, NTag } from "naive-ui";
import { computed } from "vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

const flowText = computed(() => {
  const flow = auth.flow;
  if (!flow) return "";
  switch (flow.status) {
    case "running":
      return "浏览器已在服务器端打开，请在浏览器中完成抖音登录；完成后可点击「我已完成登录」立即抓取。";
    case "success":
      return flow.message || `已抓取 ${flow.captured_count} 个参数。`;
    case "failed":
      return flow.message || "获取失败。";
    case "cancelled":
      return "已取消。";
    default:
      return "";
  }
});
</script>

<template>
  <n-modal
    :show="auth.modalOpen"
    preset="card"
    title="下载参数（Cookie）"
    style="max-width: 560px"
    @update:show="auth.modalOpen = $event"
  >
    <n-space vertical size="large">
      <div v-if="auth.status">
        <n-space size="small">
          <n-tag
            v-for="key in auth.status.required"
            :key="key"
            size="small"
            :type="auth.status.missing.includes(key) ? 'error' : 'success'"
          >
            {{ auth.status.missing.includes(key) ? "✗" : "✓" }} {{ key }}
          </n-tag>
          <n-tag size="small" :type="auth.status.has_session ? 'success' : 'default'">
            {{ auth.status.has_session ? "已登录会话" : "无登录会话" }}
          </n-tag>
          <n-tag size="small">共 {{ auth.status.cookie_count }} 个 cookie</n-tag>
        </n-space>
      </div>

      <n-alert v-if="auth.error" type="error" closable @close="auth.error = ''">
        {{ auth.error }}
      </n-alert>

      <!-- 环境缺失的提示要可选中复制：里面是用户要照着执行的命令 -->
      <n-alert v-if="!auth.browserReady" type="warning" title="浏览器环境未就绪">
        <pre class="hint">{{ auth.browserHint }}</pre>
      </n-alert>

      <n-alert
        v-if="flowText"
        :type="
          auth.flow?.status === 'success'
            ? 'success'
            : auth.flow?.status === 'failed'
              ? 'error'
              : 'info'
        "
      >
        <n-space align="center" size="small">
          <n-spin v-if="auth.flowRunning" :size="14" />
          <span>{{ flowText }}</span>
        </n-space>
      </n-alert>

      <n-space>
        <n-button
          v-if="!auth.flowRunning"
          type="primary"
          :disabled="auth.flowRunning || !auth.browserReady"
          @click="auth.startFetch()"
        >
          自动获取参数
        </n-button>
        <template v-else>
          <n-button type="primary" @click="auth.confirmFetch()">我已完成登录</n-button>
          <n-button @click="auth.cancelFetch()">取消</n-button>
        </template>
        <n-button quaternary @click="auth.refresh()">刷新状态</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<style scoped>
.hint {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-family-mono, monospace);
  font-size: 12px;
  user-select: text;
}
</style>
