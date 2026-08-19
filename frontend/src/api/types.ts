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
  /** 历史库去重命中（后端数据库关闭时恒为 false） */
  downloaded: boolean;
}

export interface WorksPage {
  source_type: string;
  items: WorkItem[];
  has_more: boolean;
  cursor: number;
}

/** 历史记录条目（后端 aweme 表投影；时间为 unix 秒） */
export interface HistoryItem {
  aweme_id: string;
  aweme_type: string;
  title: string | null;
  author_id: string | null;
  author_name: string | null;
  author_sec_uid: string | null;
  create_time: number | null;
  download_time: number | null;
  /** 落盘目录 */
  file_path: string | null;
  cover_urls: string[];
  job_id: string;
}

export interface HistoryDetail extends HistoryItem {
  /** 下载时捕获的完整作品 JSON；解析失败为 null */
  metadata: Record<string, unknown> | null;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface TopAuthor {
  sec_uid: string;
  author_name: string;
  download_count: number;
}

export interface HistoryStats {
  total: number;
  top_authors_7d: TopAuthor[];
  top_authors_30d: TopAuthor[];
}

export interface HistoryQuery {
  query?: string;
  author?: string;
  aweme_type?: string;
  author_sec_uid?: string;
  job_id?: string;
  sort?: "download_time" | "create_time";
  page?: number;
  page_size?: number;
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

/** 设置项：与 backend/server/settings.py 的 _VALIDATORS 白名单一一对应。 */
export interface NotifyProvider {
  type: "bark" | "telegram" | "webhook";
  url?: string;
  sound?: string;
  bot_token?: string;
  chat_id?: string;
}

export interface SettingsValues {
  path: string;
  video_quality: string;
  thread: number;
  rate_limit: number;
  retry_times: number;
  proxy: string;
  video: boolean;
  cover: boolean;
  music: boolean;
  avatar: boolean;
  json: boolean;
  download_pinned: boolean;
  homepage_screenshot: boolean;
  folderstyle: boolean;
  author_dir: string;
  filename_template: string;
  folder_template: string;
  comments: {
    enabled: boolean;
    include_replies: boolean;
    max_comments: number;
    page_size: number;
  };
  live: {
    max_duration_seconds: number;
    chunk_size: number;
    idle_timeout_seconds: number;
  };
  transcript: {
    enabled: boolean;
    model: string;
    output_dir: string;
    api_url: string;
    api_key_env: string;
    /** 读取时为掩码 '********'；原样回传表示不修改 */
    api_key: string;
  };
  notifications: {
    enabled: boolean;
    on_success: boolean;
    on_failure: boolean;
    providers: NotifyProvider[];
  };
}

export interface SettingsSnapshot {
  values: SettingsValues;
  /** 落盘目标；内存态运行（无 config.yml）时为 null */
  config_path: string | null;
  /** 改动后需重启服务才生效的键 */
  requires_restart_keys: string[];
  /** 被环境变量接管的键 → 环境变量名；这些键不可改（改了也会被 env 覆盖） */
  env_overrides: Record<string, string>;
}

export interface SettingsUpdateResult extends SettingsSnapshot {
  saved: boolean;
  restart_required: string[];
}

/** 局部更新：只提交改动的键；嵌套段可只带改动的子键 */
export type SettingsPatch = {
  [K in keyof SettingsValues]?: SettingsValues[K] extends object
    ? Partial<SettingsValues[K]>
    : SettingsValues[K];
};
