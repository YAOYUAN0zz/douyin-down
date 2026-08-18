<script setup lang="ts">
import {
  NBadge,
  NButton,
  NConfigProvider,
  NIcon,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NMessageProvider,
  NTag,
  darkTheme,
  dateZhCN,
  zhCN,
  type MenuOption,
} from "naive-ui";
import { computed, h, onMounted, ref, watchEffect } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AuthModal from "./components/AuthModal.vue";
import { useAuthStore } from "./stores/auth";
import { useJobsStore } from "./stores/jobs";

const auth = useAuthStore();
const jobs = useJobsStore();
const route = useRoute();

type ThemeMode = "auto" | "light" | "dark";
const themeMode = ref<ThemeMode>((localStorage.getItem("dd-theme") as ThemeMode) || "auto");
const systemDark = ref(window.matchMedia("(prefers-color-scheme: dark)").matches);
window
  .matchMedia("(prefers-color-scheme: dark)")
  .addEventListener("change", (e) => (systemDark.value = e.matches));

const isDark = computed(() =>
  themeMode.value === "auto" ? systemDark.value : themeMode.value === "dark",
);
watchEffect(() => {
  document.documentElement.dataset.theme = isDark.value ? "dark" : "light";
});
function cycleTheme() {
  const order: ThemeMode[] = ["auto", "light", "dark"];
  themeMode.value = order[(order.indexOf(themeMode.value) + 1) % order.length] ?? "auto";
  localStorage.setItem("dd-theme", themeMode.value);
}
const themeLabel = computed(
  () => ({ auto: "主题：跟随系统", light: "主题：浅色", dark: "主题：深色" })[themeMode.value],
);

function menuLink(path: string, label: string) {
  return () => h(RouterLink, { to: path }, { default: () => label });
}

const menuOptions: MenuOption[] = [
  { key: "/download", label: menuLink("/download", "⬇ 下载") },
  { key: "/works", label: menuLink("/works", "🗂 作品浏览") },
  { key: "/jobs", label: menuLink("/jobs", "📋 任务中心") },
  { key: "/history", label: menuLink("/history", "🕘 历史记录") },
  { key: "/discovery", label: menuLink("/discovery", "🔍 发现") },
  { key: "/live", label: menuLink("/live", "📡 直播录制") },
  { key: "/settings", label: menuLink("/settings", "⚙ 设置") },
];

const collapsed = ref(window.innerWidth < 768);

onMounted(() => {
  auth.init();
  jobs.start();
});
</script>

<template>
  <n-config-provider :theme="isDark ? darkTheme : null" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-layout position="absolute">
        <n-layout-header bordered class="app-header">
          <span class="app-title">Douyin Downloader</span>
          <span class="app-header-spacer"></span>

          <n-tag v-if="jobs.offline" type="error" size="small" round>
            与服务器连接中断，正在重连…
          </n-tag>
          <n-tag
            v-if="auth.loginExpired"
            type="error"
            size="small"
            round
            style="cursor: pointer"
            @click="auth.modalOpen = true"
          >
            登录已失效，点击重新登录
          </n-tag>

          <n-badge :value="jobs.activeCount" :show="jobs.activeCount > 0" :offset="[-2, 2]">
            <router-link to="/jobs" class="header-jobs-link">任务</router-link>
          </n-badge>

          <n-tag
            :type="auth.ready ? 'success' : 'warning'"
            size="small"
            round
            style="cursor: pointer"
            :title="auth.ready ? '下载参数就绪' : '缺少下载参数，点击获取'"
            @click="auth.modalOpen = true"
          >
            {{ auth.ready ? `已就绪（${auth.status?.cookie_count ?? 0} cookies）` : "参数未就绪" }}
          </n-tag>

          <n-button quaternary size="small" :title="themeLabel" @click="cycleTheme">
            <n-icon>{{ themeMode === "auto" ? "🌓" : themeMode === "light" ? "☀️" : "🌙" }}</n-icon>
          </n-button>
        </n-layout-header>

        <n-layout has-sider position="absolute" style="top: 48px">
          <n-layout-sider
            bordered
            collapse-mode="width"
            :collapsed-width="0"
            :width="180"
            :collapsed="collapsed"
            show-trigger
            @collapse="collapsed = true"
            @expand="collapsed = false"
          >
            <n-menu :value="route.path" :options="menuOptions" />
          </n-layout-sider>
          <n-layout-content content-style="padding: var(--dd-space-6);">
            <router-view />
          </n-layout-content>
        </n-layout>
      </n-layout>

      <AuthModal />
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.app-header {
  height: 48px;
  display: flex;
  align-items: center;
  gap: var(--dd-space-3);
  padding: 0 var(--dd-space-4);
}
.app-title {
  font-weight: 600;
}
.app-header-spacer {
  flex: 1;
}
.header-jobs-link {
  color: inherit;
  text-decoration: none;
  font-size: 14px;
}
</style>
