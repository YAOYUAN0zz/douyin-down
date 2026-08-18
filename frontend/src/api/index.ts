/** 按域组织的类型化 API 调用（路径与 backend/server/api 一一对应）。 */

import { apiGet, apiPost, apiRequest } from "./client";
import type {
  AuthFlowSnapshot,
  AuthStatus,
  HistoryDetail,
  HistoryPage,
  HistoryQuery,
  HistoryStats,
  JobDto,
  WorksPage,
} from "./types";

/** 把查询对象拼成 query string，跳过空值（后端把空串当未传） */
function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export interface SubmittedJob {
  job_id: string;
  status: string;
  url: string;
}

export const api = {
  download(url: string, videoQuality?: string): Promise<SubmittedJob> {
    return apiPost("/api/v1/download", { url, video_quality: videoQuality || null });
  },
  downloadBatch(urls: string[], videoQuality?: string): Promise<{ jobs: SubmittedJob[] }> {
    return apiPost("/api/v1/download/batch", { urls, video_quality: videoQuality || null });
  },
  worksList(url: string, cursor = 0, count = 20): Promise<WorksPage> {
    return apiPost("/api/v1/works/list", { url, cursor, count });
  },
  jobs(): Promise<{ jobs: JobDto[]; total: number }> {
    return apiGet("/api/v1/jobs");
  },
  job(jobId: string): Promise<JobDto> {
    return apiGet(`/api/v1/jobs/${jobId}`);
  },
  jobCancel(jobId: string): Promise<JobDto> {
    return apiPost(`/api/v1/jobs/${jobId}/cancel`);
  },
  jobRetry(jobId: string): Promise<JobDto> {
    return apiPost(`/api/v1/jobs/${jobId}/retry`);
  },
  jobDelete(jobId: string): Promise<{ deleted: string }> {
    return apiRequest(`/api/v1/jobs/${jobId}`, "DELETE");
  },
  jobsClear(): Promise<{ deleted: number }> {
    return apiPost("/api/v1/jobs/clear");
  },
  history(params: HistoryQuery = {}): Promise<HistoryPage> {
    return apiGet(`/api/v1/history${toQuery({ ...params })}`);
  },
  historyStats(limit?: number): Promise<HistoryStats> {
    return apiGet(`/api/v1/history/stats${toQuery({ limit })}`);
  },
  historyDetail(awemeId: string): Promise<HistoryDetail> {
    return apiGet(`/api/v1/history/${encodeURIComponent(awemeId)}`);
  },
  authStatus(): Promise<AuthStatus> {
    return apiGet("/api/v1/auth/status");
  },
  authFetchStart(): Promise<AuthFlowSnapshot> {
    return apiPost("/api/v1/auth/fetch");
  },
  authFetchStatus(): Promise<AuthFlowSnapshot> {
    return apiGet("/api/v1/auth/fetch/status");
  },
  authFetchConfirm(): Promise<AuthFlowSnapshot> {
    return apiPost("/api/v1/auth/fetch/confirm");
  },
  authFetchCancel(): Promise<AuthFlowSnapshot> {
    return apiPost("/api/v1/auth/fetch/cancel");
  },
};
