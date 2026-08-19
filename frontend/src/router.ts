import { createRouter, createWebHashHistory } from "vue-router";
import DownloadPage from "./pages/DownloadPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import JobsPage from "./pages/JobsPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";

// hash 模式：后端 StaticFiles 无需 SPA fallback
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/download" },
    { path: "/download", component: DownloadPage, meta: { title: "下载" } },
    // 作品浏览已并入下载页；旧书签重定向过去
    { path: "/works", redirect: "/download" },
    { path: "/jobs", component: JobsPage, meta: { title: "任务中心" } },
    { path: "/history", component: HistoryPage, meta: { title: "历史记录" } },
    { path: "/settings", component: SettingsPage, meta: { title: "设置" } },
  ],
});
