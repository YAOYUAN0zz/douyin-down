/** 任务列表：SSE 实时推送优先，断开时降级为智能轮询并自动重连。 */

import { defineStore } from "pinia";
import { api } from "../api";
import type { JobDto } from "../api/types";

const ACTIVE_POLL_MS = 2000;
const IDLE_POLL_MS = 10_000;
const SSE_RETRY_MS = 15_000;

export const useJobsStore = defineStore("jobs", {
  state: () => ({
    jobs: [] as JobDto[],
    loading: false,
    /** SSE 是否在线；离线期间由轮询兜底 */
    sseConnected: false,
    /** 连续获取失败次数；>=2 时 UI 显示连接中断横幅 */
    pollFailures: 0,
    _timer: 0 as ReturnType<typeof setTimeout> | 0,
    _sse: null as EventSource | null,
    _started: false,
  }),
  getters: {
    sorted: (s) => [...s.jobs].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    activeCount: (s) =>
      s.jobs.filter((j) => j.status === "pending" || j.status === "running").length,
    offline: (s) => !s.sseConnected && s.pollFailures >= 2,
  },
  actions: {
    start() {
      if (this._started) return;
      this._started = true;
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
          if (!this._sse) this._connectSse();
          void this.refresh();
        }
      });
      this._connectSse();
      void this.refresh();
    },

    _connectSse() {
      if (this._sse) return;
      const es = new EventSource("/api/v1/jobs/events");
      this._sse = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as { jobs: JobDto[] };
          this.jobs = data.jobs;
          this.sseConnected = true;
          this.pollFailures = 0;
          this.loading = false;
        } catch {
          // 非法帧忽略，等下一帧
        }
      };
      es.onerror = () => {
        // EventSource 自带重连；连接层彻底挂掉时切换轮询兜底并延迟重建
        this.sseConnected = false;
        if (es.readyState === EventSource.CLOSED) {
          es.close();
          this._sse = null;
          setTimeout(() => {
            if (!document.hidden) this._connectSse();
          }, SSE_RETRY_MS);
        }
        this._schedule();
      };
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
      // SSE 在线时不需要轮询；页面隐藏时由 visibilitychange 恢复
      if (this.sseConnected || document.hidden) return;
      if (this._timer) return;
      const delay = this.activeCount > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS;
      this._timer = setTimeout(() => {
        this._timer = 0;
        void this.refresh();
      }, delay);
    },

    // ---------------- 任务操作 ----------------

    async cancel(jobId: string) {
      await api.jobCancel(jobId);
      await this.refresh();
    },
    async retry(jobId: string) {
      await api.jobRetry(jobId);
      await this.refresh();
    },
    async remove(jobId: string) {
      await api.jobDelete(jobId);
      this.jobs = this.jobs.filter((j) => j.job_id !== jobId);
    },
    async clearFinished(): Promise<number> {
      const result = await api.jobsClear();
      await this.refresh();
      return result.deleted;
    },
  },
});
