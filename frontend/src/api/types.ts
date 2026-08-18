/** 与后端 server/schemas.py 对齐的类型定义。 */

export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

/** 业务码表（与 backend/server/schemas.py 保持一致） */
export const CODE_OK = 0;
export const CODE_LOGIN_REQUIRED = 40100;

export interface JobProgressCurrent {
  aweme_id: string;
  bytes_read: number;
  bytes_total: number;
}

export interface JobProgress {
  step: string;
  detail: string;
  items_total: number;
  items_done: number;
  current: JobProgressCurrent | null;
  output_dir: string | null;
  author: string | null;
}

export type JobStatus = "pending" | "running" | "success" | "partial" | "failed" | "cancelled";

export interface JobDto {
  job_id: string;
  url: string;
  options: { video_quality?: string } | null;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  total: number;
  success: number;
  failed: number;
  skipped: number;
  error: string | null;
  progress: JobProgress;
}

export interface QualityTier {
  label: string;
  width: number;
  height: number;
  bit_rate: number;
  size_bytes: number;
  fps: number;
  format: string;
  gear_name: string;
}

export interface WorkItem {
  aweme_id: string;
  desc: string;
  media_type: "video" | "images";
  duration_seconds: number;
  image_count: number;
  cover: string;
  author: string;
  create_time: number;
  download_url: string;
  size_bytes: number;
  stats: {
    digg_count: number;
    comment_count: number;
    collect_count: number;
    share_count: number;
    play_count: number;
  };
  tags: string[];
  music_title: string;
  qualities: QualityTier[];
}

export interface WorksPage {
  source_type: string;
  items: WorkItem[];
  has_more: boolean;
  cursor: number;
}

export interface AuthStatus {
  cookie_count: number;
  required: string[];
  missing: string[];
  ready: boolean;
  has_session: boolean;
}

export type AuthFlowState = "idle" | "running" | "success" | "failed" | "cancelled";

export interface AuthFlowSnapshot {
  status: AuthFlowState;
  message: string | null;
  missing: string[];
  captured_count: number;
  started_at: string | null;
  finished_at: string | null;
}
