<template>
  <div class="social-links">
    <span class="social-caption">
      维护者 ·
      <a
        class="social-author"
        href="https://github.com/YAOYUAN0zz"
        target="_blank"
        rel="noopener noreferrer"
      >
        YAOYUAN0zz
      </a>
    </span>
    <a
      class="social-upstream"
      href="https://github.com/YAOYUAN0zz/douyin-down"
      target="_blank"
      rel="noopener noreferrer"
    >
      项目仓库 · 预备作品
    </a>
    <span class="social-upstream">
      原作
      <a
        href="https://github.com/jiji262/douyin-downloader"
        target="_blank"
        rel="noopener noreferrer"
      >
        jiji262
      </a>
      · 衍生自
      <a
        href="https://github.com/shiyi-0x7f/douyin-downloader"
        target="_blank"
        rel="noopener noreferrer"
      >
        shiyi-0x7f
      </a>
    </span>
  </div>
</template>

<style scoped>
.social-links {
  display: flex;
  flex-direction: column;
  gap: var(--dd-space-2);
  padding: var(--dd-space-3) var(--dd-space-4);
  border-top: 1px solid var(--dd-border);
}
.social-caption {
  font-size: 12px;
  color: var(--dd-text-secondary);
}
.social-author {
  color: var(--dd-text);
  font-weight: 600;
  text-decoration: none;
}
.social-author:hover {
  text-decoration: underline;
}
.social-upstream {
  font-size: 11px;
  color: var(--dd-text-secondary);
}
.social-upstream a {
  color: inherit;
}
</style>
