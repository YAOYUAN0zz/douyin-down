/** 登录/下载参数状态：cookie 就绪度 + 浏览器自动获取流程。 */

import { defineStore } from "pinia";
import { api } from "../api";
import { ApiClientError, onLoginExpired } from "../api/client";
import type { AuthFlowSnapshot, AuthStatus } from "../api/types";

const FLOW_POLL_MS = 2000;

export const useAuthStore = defineStore("auth", {
  state: () => ({
    status: null as AuthStatus | null,
    flow: null as AuthFlowSnapshot | null,
    loginExpired: false,
    modalOpen: false,
    error: "" as string,
    _pollTimer: 0 as ReturnType<typeof setInterval> | 0,
  }),
  getters: {
    ready: (s) => s.status?.ready ?? false,
    flowRunning: (s) => s.flow?.status === "running",
  },
  actions: {
    init() {
      onLoginExpired(() => {
        this.loginExpired = true;
      });
      void this.refresh();
    },
    async refresh() {
      try {
        this.status = await api.authStatus();
        this.flow = await api.authFetchStatus();
        this.error = "";
        if (this.flow.status === "running") this._startPolling();
        if (this.status.ready) this.loginExpired = false;
      } catch (err) {
        this.error = (err as Error).message;
      }
    },
    async startFetch() {
      try {
        this.flow = await api.authFetchStart();
        this._startPolling();
      } catch (err) {
        if (err instanceof ApiClientError && err.httpStatus === 409) {
          // 已有会话在跑：直接进入轮询
          this._startPolling();
        } else {
          this.error = (err as Error).message;
        }
      }
    },
    async confirmFetch() {
      try {
        this.flow = await api.authFetchConfirm();
      } catch (err) {
        this.error = (err as Error).message;
      }
    },
    async cancelFetch() {
      try {
        this.flow = await api.authFetchCancel();
      } catch (err) {
        this.error = (err as Error).message;
      }
    },
    _startPolling() {
      if (this._pollTimer) return;
      this._pollTimer = setInterval(async () => {
        try {
          this.flow = await api.authFetchStatus();
        } catch {
          return; // 瞬时网络错误下一轮重试
        }
        if (this.flow.status !== "running") {
          clearInterval(this._pollTimer);
          this._pollTimer = 0;
          await this.refresh();
        }
      }, FLOW_POLL_MS);
    },
  },
});
