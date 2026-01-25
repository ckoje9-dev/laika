/**
 * API 호출 유틸리티
 */
import { API_BASE } from './state.js';

export const api = async (path, opts = {}) => {
  const { method = "GET", body, headers = {} } = opts;
  const config = { method, headers: { ...headers } };
  if (body instanceof FormData) {
    config.body = body;
  } else if (body !== undefined) {
    config.body = JSON.stringify(body);
    config.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, config);
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || res.statusText || "API 오류");
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
};
