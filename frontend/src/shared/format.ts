/** 展示层格式化工具。 */

export function formatCount(value: number | undefined | null): string {
  const n = Number(value || 0);
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}w`;
  return String(n);
}

export function formatBytes(value: number | undefined | null): string {
  const n = Number(value || 0);
  if (n <= 0) return "-";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

export function formatDuration(seconds: number | undefined | null): string {
  const s = Math.max(0, Math.floor(Number(seconds || 0)));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function formatKbps(bitRate: number | undefined | null): string {
  const n = Number(bitRate || 0);
  if (n <= 0) return "";
  return `${Math.round(n / 1000)} kbps`;
}

/** Unix 秒 → 本地日期字符串 */
export function formatUnixDate(seconds: number | undefined | null): string {
  if (!seconds) return "";
  return new Date(Number(seconds) * 1000).toLocaleDateString();
}

/** Unix 秒 → 本地日期时间字符串 */
export function formatUnixDateTime(seconds: number | undefined | null): string {
  if (!seconds) return "";
  return new Date(Number(seconds) * 1000).toLocaleString();
}

/** ISO 字符串 → 相对时间（1 分钟内=刚刚），悬停场景配合 title 展示绝对时间 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  const minute = 60_000;
  if (diff < minute) return "刚刚";
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`;
  return new Date(iso).toLocaleString();
}

export function formatAbsoluteTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
}

/** 从多行文本里提取全部链接（支持换行/空格分隔） */
export function extractUrls(text: string): string[] {
  return text
    .split(/[\s\n]+/)
    .map((s) => s.trim())
    .filter((s) => /^(https?:\/\/|v\.douyin\.com|v\.iesdouyin\.com)/i.test(s));
}
