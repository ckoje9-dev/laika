/**
 * 전역 상태 관리
 */
export const API_BASE = window.API_BASE || "http://localhost:8000";

export const state = {
  activeTab: "home",
  loggedIn: false,
  subscribed: false,
  user: null,
  users: [
    { id: "admin", pwd: "admin", role: "admin", subscribed: true },
    { id: "aaa", pwd: "aaa", role: "user", subscribed: false },
    { id: "bbb", pwd: "bbb", role: "user", subscribed: true },
  ],
  projectId: null,
  convertMode: "dwg2dxf",
  convertFiles: [],
  analyzeFiles: [],
  selectedResult: null,
  selectedOptions: {},
  layerOptions: [],
  blockOptions: [],
  templateFile: null,
  aiBorderIndex: 0,
  viewerLib: null,
  viewerLoading: null,
  parserLib: null,
  parserLoading: null,
  fontLoader: null,
  fontLoading: null,
  font: null,
};

export const statusCopy = {
  ready: "준비",
  uploading: "업로드 중",
  uploaded: "업로드 완료",
  processing: "처리 중",
  converting: "변환 중",
  parsing: "파싱 중",
  done: "완료",
  failed: "실패",
};

export const formatSize = (bytes) => {
  if (!bytes && bytes !== 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const val = bytes / 1024 ** i;
  return `${val.toFixed(val >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
};

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const $ = (id) => document.getElementById(id);
