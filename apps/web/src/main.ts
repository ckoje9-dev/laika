type ApiResult<T> = T;

type Project = { id: string };
type Version = { id: string };
type UploadInitResponse = {
  file_id: string;
  upload_path: string;
  storage_path: string;
  type: string;
  enqueued: boolean;
};
type StatusResponse = { file_id: string; status: string; message?: string | null };
type ParseResponse = { file_id: string; enqueued: boolean; message?: string | null };

const dom = {
  app: document.querySelector<HTMLDivElement>("#app"),
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function log(line: string, type: "info" | "success" | "error" = "info") {
  const stamp = new Date().toLocaleTimeString();
  const row = el("div");
  row.textContent = `[${stamp}] ${line}`;
  row.className = `log-line ${type}`;
  logBox.prepend(row);
}

function buildLayout() {
  if (!dom.app) return;
  dom.app.innerHTML = `
    <style>
      :root {
        --bg: #0f172a;
        --card: #111827;
        --accent: #38bdf8;
        --text: #e5e7eb;
        --muted: #9ca3af;
        --error: #f87171;
        --success: #34d399;
        --border: #1f2937;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 24px;
        font-family: "Segoe UI", "Noto Sans KR", sans-serif;
        background: radial-gradient(circle at 20% 20%, #1e293b, #0b1223 55%), var(--bg);
        color: var(--text);
      }
      h1 { margin: 0 0 8px; font-size: 28px; }
      p { margin: 4px 0 16px; color: var(--muted); }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 16px;
        margin-top: 16px;
      }
      .card {
        background: linear-gradient(145deg, #0b1223, #0f172a);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      }
      .card h2 { margin: 0 0 8px; font-size: 18px; }
      label { display: block; margin: 8px 0 4px; color: var(--muted); font-size: 13px; }
      input {
        width: 100%;
        padding: 10px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: #0b1223;
        color: var(--text);
        font-size: 14px;
      }
      button {
        margin-top: 12px;
        padding: 10px 14px;
        border: none;
        border-radius: 8px;
        background: var(--accent);
        color: #0b1223;
        font-weight: 600;
        cursor: pointer;
        width: 100%;
      }
      button:disabled { opacity: 0.6; cursor: not-allowed; }
      .note { font-size: 13px; color: var(--muted); margin-top: 6px; }
      .log {
        background: #0b1223;
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 10px;
        max-height: 240px;
        overflow: auto;
        font-family: "SFMono-Regular", Consolas, monospace;
        font-size: 12px;
        white-space: pre-wrap;
      }
      .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; }
      .pill.success { background: rgba(52,211,153,0.15); color: var(--success); }
      .pill.error { background: rgba(248,113,113,0.15); color: var(--error); }
      .pill.pending { background: rgba(56,189,248,0.15); color: var(--accent); }
    </style>
    <h1>Laika 파이프라인 테스트 패널</h1>
    <p>프로젝트/버전 생성 → 업로드 init → 변환 상태 조회 → 파싱 enqueue를 한 화면에서 실행합니다.</p>
    <div class="card" style="margin-bottom: 12px;">
      <h2>환경 설정</h2>
      <label>API Base URL</label>
      <input id="apiBase" value="http://localhost:8000" />
      <div class="note">docker-compose 기본 포트는 8000입니다.</div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>1) 프로젝트 생성</h2>
        <label>이름</label><input id="projectName" placeholder="demo project" />
        <label>주소</label><input id="projectAddress" placeholder="선택" />
        <label>용도</label><input id="projectPurpose" placeholder="선택" />
        <button id="createProject">프로젝트 생성</button>
        <div class="note">project_id: <span id="projectIdDisplay" class="pill"></span></div>
      </div>
      <div class="card">
        <h2>2) 버전 생성</h2>
        <label>project_id</label><input id="versionProjectId" placeholder="project_id" />
        <label>라벨</label><input id="versionLabel" placeholder="v1" />
        <button id="createVersion">버전 생성</button>
        <div class="note">version_id: <span id="versionIdDisplay" class="pill"></span></div>
      </div>
      <div class="card">
        <h2>3) 업로드 init</h2>
        <label>version_id</label><input id="uploadVersionId" placeholder="version_id" />
        <label>파일명</label><input id="uploadFilename" placeholder="sample.dwg" />
        <button id="initUpload">업로드 init 호출</button>
        <div class="note">file_id: <span id="fileIdDisplay" class="pill"></span></div>
        <div class="note">upload_path: <span id="uploadPathDisplay" class="pill"></span></div>
      </div>
      <div class="card">
        <h2>4) 변환 상태</h2>
        <label>file_id</label><input id="statusFileId" placeholder="file_id" />
        <button id="checkStatus">상태 조회</button>
        <div class="note">status: <span id="statusDisplay" class="pill"></span></div>
        <div class="note">message: <span id="statusMsgDisplay" class="pill"></span></div>
      </div>
      <div class="card">
        <h2>5) DXF 파싱 enqueue</h2>
        <label>file_id</label><input id="parseFileId" placeholder="file_id" />
        <button id="enqueueParse">dxf_parse enqueue</button>
      </div>
    </div>
    <div class="card" style="margin-top:16px;">
      <h2>로그</h2>
      <div id="log" class="log"></div>
    </div>
  `;
}

buildLayout();

const apiBaseInput = document.querySelector<HTMLInputElement>("#apiBase")!;
const projectName = document.querySelector<HTMLInputElement>("#projectName")!;
const projectAddress = document.querySelector<HTMLInputElement>("#projectAddress")!;
const projectPurpose = document.querySelector<HTMLInputElement>("#projectPurpose")!;
const projectIdDisplay = document.querySelector<HTMLSpanElement>("#projectIdDisplay")!;
const versionProjectId = document.querySelector<HTMLInputElement>("#versionProjectId")!;
const versionLabel = document.querySelector<HTMLInputElement>("#versionLabel")!;
const versionIdDisplay = document.querySelector<HTMLSpanElement>("#versionIdDisplay")!;
const uploadVersionId = document.querySelector<HTMLInputElement>("#uploadVersionId")!;
const uploadFilename = document.querySelector<HTMLInputElement>("#uploadFilename")!;
const fileIdDisplay = document.querySelector<HTMLSpanElement>("#fileIdDisplay")!;
const uploadPathDisplay = document.querySelector<HTMLSpanElement>("#uploadPathDisplay")!;
const statusFileId = document.querySelector<HTMLInputElement>("#statusFileId")!;
const statusDisplay = document.querySelector<HTMLSpanElement>("#statusDisplay")!;
const statusMsgDisplay = document.querySelector<HTMLSpanElement>("#statusMsgDisplay")!;
const parseFileId = document.querySelector<HTMLInputElement>("#parseFileId")!;
const logBox = document.querySelector<HTMLDivElement>("#log")!;

async function api<T>(path: string, init?: RequestInit & { body?: unknown }): Promise<ApiResult<T>> {
  const base = apiBaseInput.value.replace(/\/$/, "");
  const body = init?.body ? JSON.stringify(init.body) : undefined;
  const res = await fetch(base + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
    body,
  });
  const text = await res.text();
  const data = text ? (JSON.parse(text) as T) : null;
  if (!res.ok) {
    const msg = (data as any)?.detail ?? res.statusText ?? "API error";
    throw new Error(msg);
  }
  return data as T;
}

document.querySelector<HTMLButtonElement>("#createProject")?.addEventListener("click", async () => {
  try {
    const payload = {
      name: projectName.value || "demo project",
      address: projectAddress.value || null,
      purpose: projectPurpose.value || null,
    };
    const data = await api<Project>("/projects", { method: "POST", body: payload });
    projectIdDisplay.textContent = data.id;
    versionProjectId.value = data.id;
    log(`프로젝트 생성 성공: ${data.id}`, "success");
  } catch (e: any) {
    log(`프로젝트 생성 실패: ${e.message}`, "error");
  }
});

document.querySelector<HTMLButtonElement>("#createVersion")?.addEventListener("click", async () => {
  try {
    if (!versionProjectId.value) throw new Error("project_id를 입력하세요.");
    const payload = { label: versionLabel.value || null };
    const data = await api<Version>(`/projects/${versionProjectId.value}/versions`, { method: "POST", body: payload });
    versionIdDisplay.textContent = data.id;
    uploadVersionId.value = data.id;
    log(`버전 생성 성공: ${data.id}`, "success");
  } catch (e: any) {
    log(`버전 생성 실패: ${e.message}`, "error");
  }
});

document.querySelector<HTMLButtonElement>("#initUpload")?.addEventListener("click", async () => {
  try {
    if (!uploadVersionId.value) throw new Error("version_id를 입력하세요.");
    const payload = { version_id: uploadVersionId.value, filename: uploadFilename.value || "sample.dwg" };
    const data = await api<UploadInitResponse>("/uploads/init", { method: "POST", body: payload });
    fileIdDisplay.textContent = data.file_id;
    uploadPathDisplay.textContent = data.upload_path;
    statusFileId.value = data.file_id;
    parseFileId.value = data.file_id;
    log(`업로드 init 성공: file_id=${data.file_id}, 경로=${data.upload_path}`, "success");
  } catch (e: any) {
    log(`업로드 init 실패: ${e.message}`, "error");
  }
});

document.querySelector<HTMLButtonElement>("#checkStatus")?.addEventListener("click", async () => {
  try {
    if (!statusFileId.value) throw new Error("file_id를 입력하세요.");
    const data = await api<StatusResponse>(`/uploads/${statusFileId.value}/status`);
    statusDisplay.textContent = data.status;
    statusDisplay.className = `pill ${data.status}`;
    statusMsgDisplay.textContent = data.message ?? "";
    log(`상태: ${data.status}${data.message ? ` (${data.message})` : ""}`);
  } catch (e: any) {
    log(`상태 조회 실패: ${e.message}`, "error");
  }
});

document.querySelector<HTMLButtonElement>("#enqueueParse")?.addEventListener("click", async () => {
  try {
    if (!parseFileId.value) throw new Error("file_id를 입력하세요.");
    const data = await api<ParseResponse>(`/uploads/${parseFileId.value}/parse`, { method: "POST" });
    const state = data.enqueued ? "success" : "error";
    log(`dxf_parse enqueue ${data.enqueued ? "성공" : "실패"}: ${data.file_id}${data.message ? ` (${data.message})` : ""}`, state);
  } catch (e: any) {
    log(`dxf_parse enqueue 실패: ${e.message}`, "error");
  }
});
