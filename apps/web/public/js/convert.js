/**
 * DWG-DXF 변환 관련 함수
 */
import { state, statusCopy, $ } from './state.js';
import { api } from './api.js';
import { renderFileList } from './upload.js';

export function updateConvertModeUI() {
  const mode = state.convertMode === "dxf2dwg" ? "dxf2dwg" : "dwg2dxf";
  const input = $("inputConvert");
  const title = $("convertDropTitle");
  const hint = $("convertDropHint");
  const toggle = $("convertToggle");
  if (input) input.accept = mode === "dxf2dwg" ? ".dxf" : ".dwg";
  if (title) title.textContent = mode === "dxf2dwg" ? "DXF 파일 선택" : "DWG 파일 선택";
  if (hint) hint.textContent = mode === "dxf2dwg" ? "DXF → DWG 변환 (최대 100MB)" : "DWG → DXF 변환 (최대 100MB)";
  if (toggle) {
    toggle.querySelectorAll(".toggle-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }
}

export async function uploadOne(file, endpoint) {
  if (file.fileId) return file.fileId;
  file.status = "uploading";
  file.statusLabel = statusCopy.uploading;
  file.progress = 15;
  file.log = "서버로 업로드 중";
  renderFileList(file.kind);
  const fd = new FormData();
  fd.append("file", file.fileObj);
  const resp = await api(endpoint, { method: "POST", body: fd });
  file.fileId = resp.file_id || resp.id || resp.fileId;
  file.status = "uploaded";
  file.statusLabel = statusCopy.uploaded;
  file.progress = 40;
  file.log = "업로드 완료";
  renderFileList(file.kind);
  return file.fileId;
}

export async function pollStatus(file, mode) {
  return new Promise((resolve) => {
    const loop = async () => {
      try {
        const statusBase = mode === "convert" ? "/convert" : "/parsing";
        const res = await api(`${statusBase}/${file.fileId}/status`);
        const st = (res.status || "").toLowerCase();
        if (st.includes("fail") || st.includes("error")) {
          file.status = "failed";
          file.statusLabel = statusCopy.failed;
          file.progress = 100;
          file.log = res.message || "실패했습니다.";
          renderFileList(file.kind);
          return resolve(false);
        }
        const isDone = st === "done" || st === "completed" || st === "success" || res.path_dxf || res.path_original;
        if (isDone && (mode !== "convert" || res.path_dxf)) {
          file.status = "done";
          file.statusLabel = statusCopy.done;
          file.progress = 100;
          file.log = res.message || "완료되었습니다.";
          file.pathDxf = res.path_dxf || res.upload_path || res.storage_path || file.pathDxf;
          renderFileList(file.kind);
          return resolve(true);
        }
        file.status = mode === "convert" ? "processing" : "parsing";
        file.statusLabel = mode === "convert" ? statusCopy.converting : statusCopy.parsing;
        file.progress = mode === "convert" ? 70 : 80;
        file.log = res.message || (mode === "convert" ? "변환 중" : "파싱 중");
        renderFileList(file.kind);
        setTimeout(loop, 1200);
      } catch (err) {
        file.status = "failed";
        file.statusLabel = statusCopy.failed;
        file.progress = 100;
        file.log = err.message || "상태 조회 실패";
        renderFileList(file.kind);
        resolve(false);
      }
    };
    loop();
  });
}

export async function startConvert() {
  if (state.convertFiles.length === 0) {
    const msg = state.convertMode === "dxf2dwg" ? "업로드할 DXF 파일을 선택하세요." : "업로드할 DWG 파일을 선택하세요.";
    return alert(msg);
  }
  const btn = $("btnConvertStart");
  if (btn) btn.disabled = true;
  if (btn) btn.classList.add("is-loading");
  for (const file of state.convertFiles) {
    try {
      await uploadOne(file, "/convert/upload");
      await api(`/convert/${file.fileId}/convert`, { method: "POST" });
      await pollStatus(file, "convert");
    } catch (err) {
      file.status = "failed";
      file.statusLabel = statusCopy.failed;
      file.log = err.message || "변환 실패";
      renderFileList("convert");
    }
  }
  if (btn) btn.disabled = false;
  if (btn) btn.classList.remove("is-loading");
}
