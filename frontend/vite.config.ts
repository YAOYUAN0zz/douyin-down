import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";

// 后端地址从环境变量 VITE_API_PORT 读取（由 start-dev 脚本注入），禁硬编码端口
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const apiPort = env.VITE_API_PORT || "8000";
  return {
    plugins: [vue()],
    server: {
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
