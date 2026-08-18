<script setup lang="ts">
import { NButton, NCheckbox, NTag } from "naive-ui";
import type { WorkItem } from "../api/types";
import {
  formatBytes,
  formatCount,
  formatDuration,
  formatKbps,
  formatUnixDate,
} from "../shared/format";

defineProps<{
  item: WorkItem;
  selected: boolean;
}>();

defineEmits<{
  toggle: [];
  download: [];
}>();
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
    <div class="work-cover-wrap">
      <img
        v-if="item.cover"
        class="work-cover"
        :src="item.cover"
        loading="lazy"
        referrerpolicy="no-referrer"
        alt=""
      />
      <div v-else class="work-cover work-cover-empty">无封面</div>
      <n-checkbox
        class="work-check"
        :checked="selected"
        @click.stop
        @update:checked="$emit('toggle')"
      />
      <span class="work-corner">
        {{
          item.media_type === "images"
            ? `图集 ×${item.image_count}`
            : formatDuration(item.duration_seconds)
        }}
      </span>
      <n-button class="work-download" size="tiny" type="primary" @click.stop="$emit('download')">
        下载
      </n-button>
    </div>

    <div class="work-body">
      <div class="work-desc" :title="item.desc">{{ item.desc || "（无描述）" }}</div>
      <div class="work-meta">
        {{ item.author
        }}<template v-if="item.create_time"> · {{ formatUnixDate(item.create_time) }}</template>
      </div>
      <div class="work-stats">
        <span v-if="item.stats.play_count">▶ {{ formatCount(item.stats.play_count) }}</span>
        <span>👍 {{ formatCount(item.stats.digg_count) }}</span>
        <span>💬 {{ formatCount(item.stats.comment_count) }}</span>
        <span>⭐ {{ formatCount(item.stats.collect_count) }}</span>
        <span v-if="item.stats.share_count">↗ {{ formatCount(item.stats.share_count) }}</span>
      </div>
      <div v-if="item.tags.length" class="work-tags">
        <n-tag v-for="tag in item.tags.slice(0, 3)" :key="tag" size="tiny" round>#{{ tag }}</n-tag>
      </div>
      <div v-if="item.music_title" class="work-music" :title="item.music_title">
        🎵 {{ item.music_title }}
      </div>
      <div v-if="item.qualities.length" class="work-qualities">
        <div v-for="q in item.qualities" :key="q.gear_name" class="work-quality-row">
          <span class="work-quality-label">{{ q.label }}</span>
          <span>{{ q.width }}×{{ q.height }}</span>
          <span>{{ formatKbps(q.bit_rate) }}</span>
          <span class="work-quality-size">{{ formatBytes(q.size_bytes) }}</span>
        </div>
      </div>
      <div v-else-if="item.size_bytes" class="work-meta">{{ formatBytes(item.size_bytes) }}</div>
    </div>
  </div>
</template>

<style scoped>
.work-card {
  border: 1px solid var(--dd-border);
  border-radius: var(--dd-radius);
  background: var(--dd-card-bg);
  overflow: hidden;
  cursor: pointer;
  outline-offset: 2px;
}
.work-card.selected {
  border-color: #2080f0;
  box-shadow: 0 0 0 1px #2080f0;
}
.work-cover-wrap {
  position: relative;
  aspect-ratio: 3 / 4;
  background: var(--dd-border);
}
.work-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.work-cover-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.work-check {
  position: absolute;
  top: var(--dd-space-2);
  left: var(--dd-space-2);
}
.work-corner {
  position: absolute;
  right: var(--dd-space-2);
  bottom: var(--dd-space-2);
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 11px;
  border-radius: 4px;
  padding: 1px 6px;
}
.work-download {
  position: absolute;
  top: var(--dd-space-2);
  right: var(--dd-space-2);
  opacity: 0;
  transition: opacity 0.15s;
}
.work-card:hover .work-download,
.work-card:focus-within .work-download {
  opacity: 1;
}
.work-body {
  padding: var(--dd-space-2) var(--dd-space-3) var(--dd-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-1);
}
.work-desc {
  font-size: 13px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.8em;
}
.work-meta,
.work-music {
  color: var(--dd-text-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.work-stats {
  display: flex;
  gap: var(--dd-space-2);
  flex-wrap: wrap;
  color: var(--dd-text-secondary);
  font-size: 12px;
}
.work-tags {
  display: flex;
  gap: var(--dd-space-1);
  flex-wrap: wrap;
}
.work-qualities {
  border-top: 1px dashed var(--dd-border);
  padding-top: var(--dd-space-1);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.work-quality-row {
  display: flex;
  gap: var(--dd-space-2);
  font-size: 11px;
  color: var(--dd-text-secondary);
}
.work-quality-label {
  font-weight: 600;
  color: var(--dd-text);
  min-width: 42px;
}
.work-quality-size {
  margin-left: auto;
}
</style>
