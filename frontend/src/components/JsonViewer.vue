<script setup lang="ts">
/** 可折叠的 JSON 树：抖音作品元数据有 150+ 顶层键、十万级字符，
 * 平铺文本读不了，这里按层级折叠 + 按类型着色。递归引用自身（SFC 文件名）。 */
import { computed, ref } from "vue";

const props = withDefaults(
  defineProps<{
    value: unknown;
    /** 当前节点的键名；根节点不传 */
    label?: string;
    depth?: number;
    /** 深度小于此值的容器默认展开 */
    defaultExpandDepth?: number;
  }>(),
  { label: "", depth: 0, defaultExpandDepth: 1 },
);

const expanded = ref(props.depth < props.defaultExpandDepth);

const isArray = computed(() => Array.isArray(props.value));
const isObject = computed(
  () => typeof props.value === "object" && props.value !== null && !isArray.value,
);
const isContainer = computed(() => isArray.value || isObject.value);

const entries = computed<[string, unknown][]>(() => {
  if (isArray.value) return (props.value as unknown[]).map((v, i) => [String(i), v]);
  if (isObject.value) return Object.entries(props.value as Record<string, unknown>);
  return [];
});

/** 折叠时的一行概览：数组给长度，对象给前几个键 */
const summary = computed(() => {
  const count = entries.value.length;
  if (isArray.value) return `[ ${count} 项 ]`;
  const keys = entries.value.slice(0, 3).map(([k]) => k);
  const tail = count > keys.length ? ", …" : "";
  return count ? `{ ${keys.join(", ")}${tail} }` : "{ }";
});

// 超长字符串（封面/播放地址等）默认截断，点击展开全文
const LONG_TEXT = 120;
const textExpanded = ref(false);
const rawText = computed(() => (typeof props.value === "string" ? props.value : ""));
const isLongText = computed(() => rawText.value.length > LONG_TEXT);

const display = computed(() => {
  const v = props.value;
  if (v === null) return "null";
  if (typeof v === "string") {
    const text = isLongText.value && !textExpanded.value ? `${v.slice(0, LONG_TEXT)}…` : v;
    return `"${text}"`;
  }
  return String(v);
});

const valueClass = computed(() => {
  const v = props.value;
  if (v === null) return "v-null";
  if (typeof v === "string") return "v-string";
  if (typeof v === "number") return "v-number";
  if (typeof v === "boolean") return "v-bool";
  return "v-other";
});
</script>

<template>
  <div class="node">
    <template v-if="isContainer">
      <button type="button" class="row row-toggle" @click="expanded = !expanded">
        <span class="caret">{{ expanded ? "▾" : "▸" }}</span>
        <span v-if="label" class="key">{{ label }}</span>
        <span class="summary">{{ summary }}</span>
      </button>
      <div v-if="expanded" class="children">
        <JsonViewer
          v-for="[childKey, childValue] in entries"
          :key="childKey"
          :value="childValue"
          :label="childKey"
          :depth="depth + 1"
          :default-expand-depth="defaultExpandDepth"
        />
      </div>
    </template>

    <div v-else class="row">
      <span class="caret caret-blank"></span>
      <span v-if="label" class="key">{{ label }}</span>
      <span :class="['val', valueClass]">{{ display }}</span>
      <button v-if="isLongText" type="button" class="more" @click="textExpanded = !textExpanded">
        {{ textExpanded ? "收起" : "全文" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.node {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  font: inherit;
  word-break: break-all;
}
.row-toggle {
  cursor: pointer;
  border-radius: 4px;
}
.row-toggle:hover {
  background: rgba(32, 128, 240, 0.08);
}
.caret {
  flex-shrink: 0;
  width: 12px;
  color: var(--dd-text-secondary);
}
.caret-blank {
  visibility: hidden;
}
.key {
  flex-shrink: 0;
  color: var(--dd-json-key);
}
.key::after {
  content: ":";
  color: var(--dd-text-secondary);
}
.summary {
  color: var(--dd-text-secondary);
}
.children {
  margin-left: 12px;
  padding-left: 6px;
  border-left: 1px dashed var(--dd-border);
}
.val {
  min-width: 0;
}
.v-string {
  color: var(--dd-json-string);
}
.v-number {
  color: var(--dd-json-number);
}
.v-bool {
  color: var(--dd-json-bool);
}
.v-null {
  color: var(--dd-text-secondary);
  font-style: italic;
}
.more {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: #2080f0;
  cursor: pointer;
  font: inherit;
  padding: 0;
}
</style>
