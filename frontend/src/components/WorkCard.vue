<script setup lang="ts">
import { NButton, NCheckbox } from "naive-ui";
import type { WorkItem } from "../api/types";
import { formatBytes, formatCount, formatDuration, formatUnixDate } from "../shared/format";

defineProps<{
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
    <!-- 左：封面 -->
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

      <span class="cover-badge">
        {{
          item.media_type === "images"
            ? `图集 ${item.image_count} 张`
            : formatDuration(item.duration_seconds)
        }}
      </span>
    </div>

    <!-- 右：信息 + 画质行 -->
    <div class="body">
      <div class="desc" :title="item.desc">{{ item.desc || "（无描述）" }}</div>
      <div class="meta">
        <span class="meta-author">{{ item.author }}</span>
        <span v-if="item.create_time">{{ formatUnixDate(item.create_time) }}</span>
        <span v-if="item.stats.play_count">▶ {{ formatCount(item.stats.play_count) }}</span>
        <span>♥ {{ formatCount(item.stats.digg_count) }}</span>
        <span>💬 {{ formatCount(item.stats.comment_count) }}</span>
      </div>

      <div v-if="item.qualities.length" class="tiers">
        <button
          v-for="q in item.qualities"
          :key="q.gear_name"
          type="button"
          class="tier"
          :title="`${q.width}×${q.height} · 直接按 ${q.label} 下载`"
          @click.stop="$emit('download', tierParam(q.label))"
        >
          <span class="tier-label">{{ q.label }}</span>
          <span class="tier-res">{{ q.width }}×{{ q.height }}</span>
          <span class="tier-size">{{ formatBytes(q.size_bytes) }}</span>
          <span class="tier-action">⬇ 下载</span>
        </button>
        <button
          type="button"
          class="tier tier-original"
          title="最高码率 + 原画探测"
          @click.stop="$emit('download', 'original')"
        >
          <span class="tier-label">原画</span>
          <span class="tier-res">最高画质探测</span>
          <span class="tier-size"></span>
          <span class="tier-action">⬇ 下载</span>
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
  align-items: stretch;
  min-height: 184px;
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

/* 左侧封面：固定宽度，高度随卡片拉伸，图片绝对定位铺满避免塌陷 */
.cover-wrap {
  position: relative;
  width: 138px;
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

/* 右侧信息区 */
.body {
  flex: 1;
  min-width: 0;
  padding: var(--dd-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
}
.desc {
  font-size: 13px;
  line-height: 1.45;
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
  font-size: 12px;
  flex-wrap: wrap;
}
.meta-author {
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tiers {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tiers-single {
  align-items: flex-start;
}
.tier {
  display: grid;
  grid-template-columns: 48px 1fr auto 64px;
  align-items: center;
  gap: var(--dd-space-2);
  border: 1px solid var(--dd-border);
  border-radius: 8px;
  background: transparent;
  color: var(--dd-text-secondary);
  font-size: 12px;
  padding: 4px 8px;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.12s,
    background 0.12s;
}
.tier:hover {
  border-color: #2080f0;
  background: rgba(32, 128, 240, 0.08);
}
.tier:hover .tier-action {
  color: #2080f0;
  font-weight: 600;
}
.tier-label {
  font-weight: 600;
  color: var(--dd-text);
}
.tier-res {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tier-size {
  text-align: right;
}
.tier-action {
  text-align: right;
}
.tier-original .tier-label {
  color: #2080f0;
}
</style>
