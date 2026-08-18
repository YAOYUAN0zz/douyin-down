import { createRouter, createWebHashHistory } from "vue-router";
import DownloadPage from "./pages/DownloadPage.vue";
import JobsPage from "./pages/JobsPage.vue";
import PlaceholderPage from "./pages/PlaceholderPage.vue";
import WorksPage from "./pages/WorksPage.vue";

// hash 模式：后端 StaticFiles 无需 SPA fallback
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/download" },
    { path: "/download", component: DownloadPage, meta: { title: "下载" } },
    { path: "/works", component: WorksPage, meta: { title: "作品浏览" } },
    { path: "/jobs", component: JobsPage, meta: { title: "任务中心" } },
    {
      path: "/history",
      component: PlaceholderPage,
      meta: { title: "历史记录", stage: "M4" },
    },
    { path: "/settings", component: PlaceholderPage, meta: { title: "设置", stage: "M3" } },
  ],
});
