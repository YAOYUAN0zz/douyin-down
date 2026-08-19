<script setup lang="ts">
/** 设置页：在 UI 里改配置，免去用户手改 config.yml。
 *
 * 只提交改动过的键（后端 PUT /settings 支持局部更新），因此不会把用户手写在
 * config.yml 里、UI 未覆盖的键冲掉。
 */
import {
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NInput,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSkeleton,
  NSpace,
  NSwitch,
  NTag,
  useMessage,
} from "naive-ui";
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { NotifyProvider, SettingsPatch, SettingsValues } from "../api/types";

const message = useMessage();

/** 服务器上的当前值，用作 diff 基线与「重置」目标 */
const baseline = ref<SettingsValues | null>(null);
const draft = ref<SettingsValues | null>(null);
const configPath = ref<string | null>(null);
const restartKeys = ref<string[]>([]);
/** 被环境变量接管的键 → 变量名。这些字段禁用编辑：改了也会在重启后被 env 覆盖。 */
const envOverrides = ref<Record<string, string>>({});

const loading = ref(true);
const loadError = ref("");
const saving = ref(false);
/** 上次保存后仍需重启才生效的键，保存成功后提示，重启前一直可见 */
const pendingRestart = ref<string[]>([]);

const QUALITY_OPTIONS = [
  { value: "original", label: "原画（探测上传原片，最慢）" },
  { value: "highest", label: "最高转码档（推荐）" },
  { value: "1440p", label: "1440p" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
  { value: "540p", label: "540p" },
  { value: "480p", label: "480p" },
  { value: "360p", label: "360p" },
  { value: "lowest", label: "最低档（省流量）" },
];

const AUTHOR_DIR_OPTIONS = [
  { value: "nickname", label: "昵称" },
  { value: "sec_uid", label: "ID" },
  { value: "nickname_uid", label: "昵称_ID" },
];

/** 保存内容开关：一处声明，模板里循环渲染 */
const SAVE_TOGGLES: Array<{ key: keyof SettingsValues; label: string; hint: string }> = [
  { key: "video", label: "视频文件", hint: "作品本体，关闭后只保存下方勾选的附带产物" },
  { key: "cover", label: "封面图", hint: "作品原始封面" },
  { key: "music", label: "背景音乐", hint: "作品使用的音乐音频" },
  { key: "avatar", label: "作者头像", hint: "保存到作者目录下" },
  { key: "json", label: "原始 JSON", hint: "接口返回的完整作品元数据" },
  { key: "download_pinned", label: "包含置顶作品", hint: "下载博主主页时是否含置顶" },
  { key: "homepage_screenshot", label: "主页截图", hint: "在作者目录保存一张主页首屏截图" },
];

const NOTIFY_TYPE_OPTIONS = [
  { value: "bark", label: "Bark" },
  { value: "telegram", label: "Telegram" },
  { value: "webhook", label: "Webhook" },
];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const snapshot = await api.settings();
    baseline.value = snapshot.values;
    draft.value = clone(snapshot.values);
    configPath.value = snapshot.config_path;
    restartKeys.value = snapshot.requires_restart_keys;
    envOverrides.value = snapshot.env_overrides;
  } catch (err) {
    loadError.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);

/** 只含改动键的补丁；嵌套段整体比较、整体提交（后端对 dict 做浅合并） */
const patch = computed<SettingsPatch>(() => {
  const result: Record<string, unknown> = {};
  if (!draft.value || !baseline.value) return result;
  for (const key of Object.keys(draft.value) as Array<keyof SettingsValues>) {
    const next = draft.value[key];
    const prev = baseline.value[key];
    if (JSON.stringify(next) !== JSON.stringify(prev)) result[key] = next;
  }
  return result;
});

const dirtyKeys = computed(() => Object.keys(patch.value));
const isDirty = computed(() => dirtyKeys.value.length > 0);

/** 本次改动里是否碰了需重启才生效的键 */
const touchedRestartKeys = computed(() =>
  restartKeys.value.filter((key) => dirtyKeys.value.includes(key)),
);

const envOverrideList = computed(() => Object.entries(envOverrides.value));
function envTakenBy(key: string): string | undefined {
  return envOverrides.value[key];
}

async function save() {
  if (!isDirty.value) return;
  saving.value = true;
  try {
    const result = await api.settingsUpdate(patch.value);
    baseline.value = result.values;
    draft.value = clone(result.values);
    if (result.restart_required.length) {
      pendingRestart.value = result.restart_required;
    }
    message.success(result.saved ? "已保存到 config.yml" : "已生效（未配置文件路径，重启后失效）");
  } catch (err) {
    message.error((err as Error).message);
  } finally {
    saving.value = false;
  }
}

function reset() {
  if (!baseline.value) return;
  draft.value = clone(baseline.value);
}

function addProvider() {
  draft.value?.notifications.providers.push({ type: "bark", url: "" });
}

function removeProvider(index: number) {
  draft.value?.notifications.providers.splice(index, 1);
}

/** 切换渠道类型时清掉上一类型的专属字段，避免提交无关残留 */
function onProviderTypeChange(provider: NotifyProvider, type: NotifyProvider["type"]) {
  provider.type = type;
  delete provider.url;
  delete provider.sound;
  delete provider.bot_token;
  delete provider.chat_id;
  if (type === "telegram") {
    provider.bot_token = "";
    provider.chat_id = "";
  } else {
    provider.url = "";
  }
}
</script>

<template>
  <div class="settings">
    <n-skeleton v-if="loading" text :repeat="8" />

    <n-alert v-else-if="loadError" type="error" title="加载设置失败">
      <div class="load-error">
        <span>{{ loadError }}</span>
        <n-button size="small" @click="load">重试</n-button>
      </div>
    </n-alert>

    <template v-else-if="draft">
      <!-- 操作栏：常驻顶部，改动数量与保存入口始终可见 -->
      <div class="settings-bar">
        <div class="settings-bar-info">
          <span v-if="configPath" class="settings-path" :title="configPath">
            写入 {{ configPath }}
          </span>
          <span v-else class="settings-path">未指定配置文件，改动仅在本次运行内有效</span>
          <n-tag v-if="isDirty" type="warning" size="small" :bordered="false">
            {{ dirtyKeys.length }} 项未保存
          </n-tag>
        </div>
        <n-space :size="8">
          <n-button size="small" :disabled="!isDirty || saving" @click="reset">撤销改动</n-button>
          <n-button
            type="primary"
            size="small"
            :loading="saving"
            :disabled="!isDirty"
            @click="save"
          >
            保存
          </n-button>
        </n-space>
      </div>

      <n-alert v-if="envOverrideList.length" type="info" :bordered="false">
        以下配置由环境变量接管，改这里无效（重启后会被覆盖），请改环境变量本身：
        {{ envOverrideList.map(([key, env]) => `${key} ← ${env}`).join("，") }}
      </n-alert>

      <n-alert v-if="touchedRestartKeys.length" type="warning" :bordered="false">
        {{ touchedRestartKeys.join("、") }} 需要重启服务后才会生效，其余改动保存即生效。
      </n-alert>
      <n-alert
        v-else-if="pendingRestart.length"
        type="info"
        :bordered="false"
        closable
        @close="pendingRestart = []"
      >
        {{ pendingRestart.join("、") }} 已保存，重启服务后生效。
      </n-alert>

      <n-card title="下载与存储" size="small">
        <div class="field-grid">
          <label class="field">
            <span class="field-label">下载目录</span>
            <n-input
              v-model:value="draft.path"
              placeholder="./Downloaded/"
              :disabled="!!envTakenBy('path')"
            />
            <span class="field-hint">
              {{
                envTakenBy("path")
                  ? `由环境变量 ${envTakenBy("path")} 接管`
                  : "相对路径以服务启动目录为基准"
              }}
            </span>
          </label>

          <label class="field">
            <span class="field-label">视频画质</span>
            <n-select v-model:value="draft.video_quality" :options="QUALITY_OPTIONS" />
            <span class="field-hint">原画每条作品多一次探测请求，明显更慢</span>
          </label>

          <label class="field">
            <span class="field-label">并发数</span>
            <n-input-number
              v-model:value="draft.thread"
              :min="1"
              :max="32"
              :disabled="!!envTakenBy('thread')"
              class="field-number"
            />
            <span class="field-hint">
              {{
                envTakenBy("thread")
                  ? `由环境变量 ${envTakenBy("thread")} 接管`
                  : "调高易触发风控；出现大量失败时先调回 5"
              }}
            </span>
          </label>

          <label class="field">
            <span class="field-label">请求速率上限（次/秒）</span>
            <n-input-number
              v-model:value="draft.rate_limit"
              :min="0.1"
              :max="20"
              :step="0.5"
              class="field-number"
            />
            <span class="field-hint">对抖音接口的调用频率</span>
          </label>

          <label class="field">
            <span class="field-label">失败重试次数</span>
            <n-input-number
              v-model:value="draft.retry_times"
              :min="0"
              :max="10"
              class="field-number"
            />
          </label>

          <label class="field">
            <span class="field-label">代理</span>
            <n-input
              v-model:value="draft.proxy"
              placeholder="留空表示不使用代理"
              :disabled="!!envTakenBy('proxy')"
            />
            <span class="field-hint">
              {{
                envTakenBy("proxy")
                  ? `由环境变量 ${envTakenBy("proxy")} 接管`
                  : "例：http://127.0.0.1:7890"
              }}
            </span>
          </label>
        </div>
      </n-card>

      <n-card title="保存内容" size="small">
        <div class="toggle-grid">
          <div v-for="item in SAVE_TOGGLES" :key="item.key" class="toggle-row">
            <n-switch v-model:value="draft[item.key] as boolean" size="small" />
            <div class="toggle-text">
              <span class="field-label">{{ item.label }}</span>
              <span class="field-hint">{{ item.hint }}</span>
            </div>
          </div>
        </div>
      </n-card>

      <n-card title="命名与目录" size="small">
        <div class="field-grid">
          <div class="field">
            <span class="field-label">作者目录命名</span>
            <n-radio-group v-model:value="draft.author_dir" size="small">
              <n-radio-button
                v-for="opt in AUTHOR_DIR_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </n-radio-group>
            <span class="field-hint">只影响后续下载，不会迁移已存在的目录</span>
          </div>

          <div class="field">
            <span class="field-label">每个作品单独建目录</span>
            <n-switch v-model:value="draft.folderstyle" size="small" />
            <span class="field-hint">关闭后所有文件平铺在作者目录下</span>
          </div>

          <label class="field">
            <span class="field-label">文件名模板</span>
            <n-input v-model:value="draft.filename_template" />
            <span class="field-hint">
              可用：{id} {title} {author} {date} {type} 等，必须含 {id}
            </span>
          </label>

          <label class="field">
            <span class="field-label">目录名模板</span>
            <n-input v-model:value="draft.folder_template" />
            <span class="field-hint">同上，必须含 {id} 以免重名覆盖</span>
          </label>
        </div>
      </n-card>

      <n-collapse>
        <n-collapse-item title="评论采集" name="comments">
          <template #header-extra>
            <n-tag v-if="draft.comments.enabled" size="small" type="success" :bordered="false">
              已开启
            </n-tag>
          </template>
          <div class="field-grid">
            <div class="field">
              <span class="field-label">采集评论</span>
              <n-switch v-model:value="draft.comments.enabled" size="small" />
              <span class="field-hint">每个作品额外生成 *_comments.json</span>
            </div>
            <div class="field">
              <span class="field-label">包含楼中楼回复</span>
              <n-switch
                v-model:value="draft.comments.include_replies"
                size="small"
                :disabled="!draft.comments.enabled"
              />
            </div>
            <label class="field">
              <span class="field-label">最多采集条数</span>
              <n-input-number
                v-model:value="draft.comments.max_comments"
                :min="0"
                :max="100000"
                :disabled="!draft.comments.enabled"
                class="field-number"
              />
              <span class="field-hint">0 表示不限</span>
            </label>
            <label class="field">
              <span class="field-label">每页条数</span>
              <n-input-number
                v-model:value="draft.comments.page_size"
                :min="1"
                :max="50"
                :disabled="!draft.comments.enabled"
                class="field-number"
              />
            </label>
          </div>
        </n-collapse-item>

        <n-collapse-item title="直播录制" name="live">
          <div class="field-grid">
            <label class="field">
              <span class="field-label">最长录制时长（秒）</span>
              <n-input-number
                v-model:value="draft.live.max_duration_seconds"
                :min="0"
                :max="86400"
                class="field-number"
              />
              <span class="field-hint">0 表示录到主播下播</span>
            </label>
            <label class="field">
              <span class="field-label">无数据超时（秒）</span>
              <n-input-number
                v-model:value="draft.live.idle_timeout_seconds"
                :min="5"
                :max="600"
                class="field-number"
              />
            </label>
            <label class="field">
              <span class="field-label">分块大小（字节）</span>
              <n-input-number
                v-model:value="draft.live.chunk_size"
                :min="1024"
                :max="1048576"
                :step="1024"
                class="field-number"
              />
            </label>
          </div>
        </n-collapse-item>

        <n-collapse-item title="完成通知" name="notifications">
          <template #header-extra>
            <n-tag v-if="draft.notifications.enabled" size="small" type="success" :bordered="false">
              已开启
            </n-tag>
          </template>
          <div class="field-grid">
            <div class="field">
              <span class="field-label">启用通知</span>
              <n-switch v-model:value="draft.notifications.enabled" size="small" />
            </div>
            <div class="field">
              <span class="field-label">成功时通知</span>
              <n-switch
                v-model:value="draft.notifications.on_success"
                size="small"
                :disabled="!draft.notifications.enabled"
              />
            </div>
            <div class="field">
              <span class="field-label">失败时通知</span>
              <n-switch
                v-model:value="draft.notifications.on_failure"
                size="small"
                :disabled="!draft.notifications.enabled"
              />
            </div>
          </div>

          <div class="providers">
            <div
              v-for="(provider, index) in draft.notifications.providers"
              :key="index"
              class="provider-row"
            >
              <n-radio-group
                :value="provider.type"
                size="small"
                @update:value="(v: NotifyProvider['type']) => onProviderTypeChange(provider, v)"
              >
                <n-radio-button
                  v-for="opt in NOTIFY_TYPE_OPTIONS"
                  :key="opt.value"
                  :value="opt.value"
                  :label="opt.label"
                />
              </n-radio-group>

              <template v-if="provider.type === 'telegram'">
                <n-input v-model:value="provider.bot_token" placeholder="Bot Token" />
                <n-input v-model:value="provider.chat_id" placeholder="Chat ID" />
              </template>
              <template v-else>
                <n-input
                  v-model:value="provider.url"
                  :placeholder="
                    provider.type === 'bark' ? 'https://api.day.app/你的Key' : '推送 URL'
                  "
                />
                <n-input
                  v-if="provider.type === 'bark'"
                  v-model:value="provider.sound"
                  placeholder="提示音（可选）"
                />
              </template>

              <n-button size="small" quaternary type="error" @click="removeProvider(index)">
                删除
              </n-button>
            </div>
            <n-button size="small" dashed @click="addProvider">+ 添加通知渠道</n-button>
          </div>
        </n-collapse-item>
      </n-collapse>
    </template>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-4);
}
.load-error {
  display: flex;
  align-items: center;
  gap: var(--dd-space-3);
  flex-wrap: wrap;
}
.settings-bar {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dd-space-3);
  flex-wrap: wrap;
  padding: var(--dd-space-3) var(--dd-space-4);
  background: var(--dd-card-bg);
  border: 1px solid var(--dd-border);
  border-radius: var(--dd-radius);
}
.settings-bar-info {
  display: flex;
  align-items: center;
  gap: var(--dd-space-2);
  min-width: 0;
}
.settings-path {
  font-size: 12px;
  color: var(--dd-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--dd-space-4);
}
.field {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--dd-space-2);
}
.field-label {
  font-size: 13px;
  font-weight: 600;
}
.field-hint {
  font-size: 12px;
  color: var(--dd-text-secondary);
  line-height: 1.5;
}
.field-number {
  width: 160px;
}
.toggle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--dd-space-4);
}
.toggle-row {
  display: flex;
  align-items: flex-start;
  gap: var(--dd-space-3);
}
.toggle-text {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-1);
  min-width: 0;
}
.providers {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-3);
  margin-top: var(--dd-space-4);
  padding-top: var(--dd-space-4);
  border-top: 1px solid var(--dd-border);
}
.provider-row {
  display: flex;
  align-items: center;
  gap: var(--dd-space-2);
  flex-wrap: wrap;
}
.provider-row :deep(.n-input) {
  flex: 1;
  min-width: 180px;
}
</style>
