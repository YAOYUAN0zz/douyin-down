/** 任务列表：智能轮询（有活动任务 2s，空闲 10s，页面隐藏暂停），失败可见。 */

import { defineStore } from "pinia";
import { api } from "../api";
import type { JobDto } from "../api/types";

const ACTIVE_POLL_MS = 2000;
const IDLE_POLL_MS = 10_000;

export const useJobsStore = defineStore("jobs", {
  state: () => ({
    jobs: [] as JobDto[],
    loading: false,
    /** 连续轮询失败次数；>0 时 UI 显示连接中断横幅 */
    pollFailures: 0,
    _timer: 0 as ReturnType<typeof setTimeout> | 0,
    _started: false,
  }),
  getters: {
    sorted: (s) => [...s.jobs].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    activeCount: (s) =>
      s.jobs.filter((j) => j.status === "pending" || j.status === "running").length,
    offline: (s) => s.pollFailures >= 2,
  },
  actions: {
    start() {
      if (this._started) return;
      this._started = true;
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) void this.refresh();
      });
      void this.refresh();
    },
    async refresh() {
      if (this._timer) {
        clearTimeout(this._timer);
        this._timer = 0;
      }
      this.loading = this.jobs.length === 0;
      try {
        const data = await api.jobs();
        this.jobs = data.jobs;
        this.pollFailures = 0;
      } catch {
        this.pollFailures += 1;
      } finally {
        this.loading = false;
        this._schedule();
      }
    },
    _schedule() {
      if (document.hidden) return; // visibilitychange 恢复时重新拉取
      const delay = this.activeCount > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS;
      this._timer = setTimeout(() => void this.refresh(), delay);
    },
  },
});
