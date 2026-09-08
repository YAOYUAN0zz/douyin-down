<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NCheckbox } from "naive-ui";
import type { WorkItem } from "../api/types";
import {
  formatBytes,
  formatCount,
  formatDuration,
  formatKbps,
  formatUnixDate,
  formatUnixDateTime,
} from "../shared/format";

const MAX_VISIBLE_TIERS = 2;
const expanded = ref(false);
const metaOpen = ref(false);

const props = defineProps<{
  item: WorkItem;
  selected: boolean;
}>();

defineEmits<{
  toggle: [];
  /** 直接按指定画质下载；undefined = 跟随全局配置 */
  download: [quality?: string];
}>();

// 下载端支持的档位（与后端 ALLOWED_VIDEO_QUALITIES 对齐）
const TIER_STEPS = [1440, 1080, 720, 540, 480, 360];

/** 把阶梯 label（如 544p/1088p）就近映射为可下载档位参数 */
function tierParam(label: string): string {
  const n = parseInt(label, 10);
  if (Number.isNaN(n)) return "highest";
  if (n > 1440) return "original";
  for (const step of TIER_STEPS) {
    if (n >= step) return `${step}p`;
  }
  return "360p";
}

/** 元数据明细行；值为空的条目不出现，避免展开后一堆「-」 */
const metaRows = computed<Array<{ label: string; value: string }>>(() => {
  const it = props.item;
  const top = it.qualities[0];
  const rows: Array<{ label: string; value: string }> = [];
  const push = (label: string, value: string | number | undefined | null) => {
    const text = String(value ?? "").trim();
    if (text) rows.push({ label, value: text });
  };

  push("作品 ID", it.aweme_id);
  push("类型", it.media_type === "images" ? `图集 · ${it.image_count} 张` : "视频");
  if (it.media_type === "video" && it.duration_seconds) {
    push("时长", formatDuration(it.duration_seconds));
  }
  push("发布时间", formatUnixDateTime(it.create_time));
  if (top) {
    push("分辨率", top.width && top.height ? `${top.width}×${top.height}` : "");
    push("帧率", top.fps ? `${top.fps} fps` : "");
    push("码率", formatKbps(top.bit_rate));
    push("封装格式", top.format);
  }
  if (it.size_bytes) push("最高档大小", formatBytes(it.size_bytes));
  if (it.original_size_bytes) push("原画大小", formatBytes(it.original_size_bytes));
  // 抖音对部分作品不返回播放/收藏等计数，0 一律省略而不是显示「0」
  const stat = (label: string, value: number) => {
    if (value > 0) push(label, formatCount(value));
  };
  stat("播放", it.stats.play_count);
  stat("点赞", it.stats.digg_count);
  stat("评论", it.stats.comment_count);
  stat("收藏", it.stats.collect_count);
  stat("分享", it.stats.share_count);
  push("音乐", it.music_title);
  return rows;
});
</script>

<template>
  <div
    class="work-card"
    :class="{ selected }"
    role="checkbox"
    :aria-checked="selected"
    tabindex="0"
    @click="$emit('toggle')"
    @keydown.space.prevent="$emit('toggle')"
    @keydown.enter.prevent="$emit('toggle')"
  >
    <!-- 上：封面 -->
    <div class="cover-wrap">
      <img
        v-if="item.cover"
        class="cover"
        :src="item.cover"
        loading="lazy"
        referrerpolicy="no-referrer"
        alt=""
      />
      <div v-else class="cover cover-empty">无封面</div>

      <n-checkbox
        class="check"
        :checked="selected"
        aria-label="选择"
        @click.stop
        @update:checked="$emit('toggle')"
      />

      <span v-if="item.downloaded" class="downloaded-badge" title="历史记录中已有该作品">
        已下载
      </span>

      <span class="cover-badge">
        {{
          item.media_type === "images"
            ? `图集 ${item.image_count} 张`
            : formatDuration(item.duration_seconds)
        }}
      </span>
    </div>

    <!-- 下：信息 + 画质行 -->
    <div class="body">
      <div class="desc" :title="item.desc">{{ item.desc || "（无描述）" }}</div>
      <div class="meta">
        <span class="meta-author">{{ item.author }}</span>
        <span v-if="item.create_time">{{ formatUnixDate(item.create_time) }}</span>
        <span v-if="item.stats.play_count">▶ {{ formatCount(item.stats.play_count) }}</span>
        <span>♥ {{ formatCount(item.stats.digg_count) }}</span>
        <span>💬 {{ formatCount(item.stats.comment_count) }}</span>
      </div>

      <!-- 元数据：默认折叠，展开后按 label/value 平铺 -->
      <div class="meta-block">
        <button type="button" class="meta-toggle" @click.stop="metaOpen = !metaOpen">
          {{ metaOpen ? "▾" : "▸" }} 元数据
        </button>
        <template v-if="metaOpen">
          <dl class="meta-list">
            <template v-for="row in metaRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </template>
          </dl>
          <div v-if="item.tags.length" class="meta-tags">
            <span v-for="tag in item.tags" :key="tag" class="meta-tag">#{{ tag }}</span>
          </div>
        </template>
      </div>

      <div v-if="item.qualities.length" class="tiers">
        <button
          type="button"
          class="tier tier-original"
          title="最高码率 + 原画探测"
          @click.stop="$emit('download', 'original')"
        >
          原画
          <span v-if="item.original_size_bytes" class="tier-size">{{
            formatBytes(item.original_size_bytes)
          }}</span>
          <span class="tier-dl">⬇</span>
        </button>
        <button
          v-for="q in expanded ? item.qualities : item.qualities.slice(0, MAX_VISIBLE_TIERS)"
          :key="q.gear_name"
          type="button"
          class="tier"
          :title="`${q.width}×${q.height} · 直接按 ${q.label} 下载`"
          @click.stop="$emit('download', tierParam(q.label))"
        >
          <b>{{ q.label }}</b>
          <span v-if="q.size_bytes" class="tier-size">{{ formatBytes(q.size_bytes) }}</span>
          <span class="tier-dl">⬇</span>
        </button>
        <button
          v-if="!expanded && item.qualities.length > MAX_VISIBLE_TIERS"
          type="button"
          class="tier tier-more"
          @click.stop="expanded = true"
        >
          +{{ item.qualities.length - MAX_VISIBLE_TIERS }}
        </button>
      </div>
      <div v-else class="tiers tiers-single">
        <n-button size="small" type="primary" @click.stop="$emit('download', undefined)">
          ⬇ 下载{{ item.media_type === "images" ? "图集" : "" }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.work-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--dd-border);
  border-radius: 12px;
  background: var(--dd-card-bg);
  overflow: hidden;
  cursor: pointer;
  outline-offset: 2px;
  transition:
    box-shadow 0.15s ease,
    border-color 0.15s ease;
}
.work-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}
.work-card.selected {
  border-color: #2080f0;
  box-shadow: 0 0 0 2px rgba(32, 128, 240, 0.35);
}

/* 封面：固定 16:9 容器，图片铺满 */
.cover-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  flex-shrink: 0;
  background: var(--dd-border);
}
.cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cover-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.check {
  position: absolute;
  top: var(--dd-space-2);
  left: var(--dd-space-2);
  z-index: 1;
  background: rgba(0, 0, 0, 0.35);
  border-radius: 4px;
  padding: 2px;
}
.downloaded-badge {
  position: absolute;
  right: var(--dd-space-2);
  top: var(--dd-space-2);
  background: rgba(24, 160, 88, 0.9);
  color: #fff;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
}
.cover-badge {
  position: absolute;
  right: var(--dd-space-2);
  bottom: var(--dd-space-2);
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
}

/* 信息区 */
.body {
  flex: 1;
  min-width: 0;
  padding: var(--dd-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
}
.desc {
  font-size: 14px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.meta {
  display: flex;
  gap: var(--dd-space-3);
  color: var(--dd-text-secondary);
  font-size: 13px;
  flex-wrap: wrap;
}
.meta-author {
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 元数据折叠区 */
.meta-block {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
}
.meta-toggle {
  align-self: flex-start;
  border: none;
  background: transparent;
  padding: 0;
  color: var(--dd-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.meta-toggle:hover {
  color: #2080f0;
}
.meta-list {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px var(--dd-space-2);
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}
.meta-list dt {
  color: var(--dd-text-secondary);
  white-space: nowrap;
}
.meta-list dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}
.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dd-space-1);
}
.meta-tag {
  border-radius: 4px;
  background: rgba(32, 128, 240, 0.1);
  color: #2080f0;
  font-size: 11px;
  padding: 1px 6px;
}

.tiers {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tiers-single {
  align-items: flex-start;
}
.tier {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--dd-border);
  border-radius: 999px;
  background: transparent;
  color: var(--dd-text);
  font-size: 13px;
  line-height: 1;
  padding: 6px 12px;
  cursor: pointer;
  transition:
    border-color 0.12s,
    background 0.12s;
}
.tier b {
  font-weight: 600;
}
.tier:hover {
  border-color: #2080f0;
  background: rgba(32, 128, 240, 0.08);
}
.tier:hover .tier-dl {
  color: #2080f0;
  font-weight: 700;
}
.tier-size {
  color: var(--dd-text-secondary);
}
.tier-dl {
  color: var(--dd-text-secondary);
}
.tier-original {
  border-color: rgba(32, 128, 240, 0.5);
  color: #2080f0;
  font-weight: 600;
}
.tier-more {
  color: var(--dd-text-secondary);
  font-size: 12px;
  padding: 6px 10px;
}
</style>
