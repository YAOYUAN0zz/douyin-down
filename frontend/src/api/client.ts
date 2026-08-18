/** fetch 薄封装：统一响应模型解包、错误对象化、401 全局广播。 */

import { CODE_LOGIN_REQUIRED, type ApiEnvelope } from "./types";

export class ApiClientError extends Error {
  readonly code: number;
  readonly httpStatus: number;

  constructor(code: number, httpStatus: number, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

type LoginExpiredListener = () => void;
const loginExpiredListeners = new Set<LoginExpiredListener>();

/** 任意接口返回登录失效码时触发（auth store 订阅后弹全局横幅）。 */
export function onLoginExpired(listener: LoginExpiredListener): () => void {
  loginExpiredListeners.add(listener);
  return () => loginExpiredListeners.delete(listener);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    throw new ApiClientError(-1, 0, `无法连接服务器：${(err as Error).message}`);
  }

  let body: ApiEnvelope<T>;
  try {
    body = (await resp.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiClientError(-1, resp.status, `服务器返回了非预期响应（HTTP ${resp.status}）`);
  }

  if (body.code !== 0) {
    if (body.code === CODE_LOGIN_REQUIRED) {
      loginExpiredListeners.forEach((fn) => fn());
    }
    throw new ApiClientError(body.code, resp.status, body.message);
  }
  return body.data;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
}

export function apiRequest<T>(path: string, method: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
}
