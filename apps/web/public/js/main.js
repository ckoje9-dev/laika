/**
 * 메인 진입점 - 이벤트 바인딩 및 초기화
 */
import { state, $, API_BASE } from './state.js';
import { api } from './api.js';
import { doLogin, doLogout, doSignup, updateUserUI } from './auth.js';
import { setTab, setDetailTab } from './tabs.js';
import { renderFileList, addFiles, bindDropzone } from './upload.js';
import { startConvert, updateConvertModeUI } from './convert.js';
import { startParse, loadParsed, loadEntitiesTable, refreshSemanticSummary } from './parse.js';
import { initSmartSelects, applyTemplateSelections, setLoadParsedFn } from './smart-select.js';
import { updateResultList, renderResultView, renderAiResultView } from './results.js';

// Wire up circular dependency
setLoadParsedFn(loadParsed);

function bindEvents() {
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setTab(tab.dataset.tab)));
  document.querySelectorAll("[data-tab-jump]").forEach((btn) =>
    btn.addEventListener("click", () => setTab(btn.dataset.tabJump))
  );
  $("btnHome").onclick = () => setTab("home");
  $("btnLogin").onclick = () => (state.loggedIn ? doLogout() : setTab("login"));
  $("btnSignup").onclick = () => setTab(state.loggedIn ? "home" : "signup");
  $("btnDoLogin").onclick = () => doLogin($("loginId").value.trim(), $("loginPwd").value);
  ["loginId", "loginPwd"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        doLogin($("loginId").value.trim(), $("loginPwd").value);
      }
    });
  });
  $("btnDoSignup").onclick = () => doSignup($("signupId").value.trim(), $("signupPwd").value, $("signupPwd2").value);

  const btnSubscribe = $("btnSubscribe");
  if (btnSubscribe) {
    btnSubscribe.onclick = () => {
      if (!state.loggedIn) {
        alert("로그인 후 구독할 수 있습니다.");
        return setTab("login");
      }
      state.subscribed = true;
      if (state.user) state.user.subscribed = true;
      updateUserUI();
      alert("구독이 활성화되었습니다.");
    };
  }

  const btnNotify = $("btnNotify");
  if (btnNotify) btnNotify.onclick = () => alert("준비되면 이메일로 안내해드리겠습니다.");

  $("dropConvert").addEventListener("click", () => $("inputConvert").click());
  $("dropAnalyze").addEventListener("click", () => $("inputAnalyze").click());
  $("inputConvert").addEventListener("change", (e) => addFiles("convert", e.target.files));
  $("inputAnalyze").addEventListener("change", (e) => addFiles("analyze", e.target.files));

  const convertToggle = $("convertToggle");
  if (convertToggle) {
    convertToggle.addEventListener("click", (e) => {
      const btn = e.target.closest(".toggle-btn");
      if (!btn) return;
      const nextMode = btn.dataset.mode;
      if (!nextMode || nextMode === state.convertMode) return;
      if (state.convertFiles.length > 0) {
        const ok = confirm("현재 업로드된 파일이 있습니다. 변환 방향을 바꾸면 목록이 초기화됩니다. 계속할까요?");
        if (!ok) return;
        state.convertFiles = [];
        renderFileList("convert");
      }
      state.convertMode = nextMode;
      updateConvertModeUI();
    });
  }

  bindDropzone($("dropConvert"), "convert");
  bindDropzone($("dropAnalyze"), "analyze");
  $("btnConvertStart").onclick = startConvert;

  $("btnConvertDownload").onclick = async () => {
    const doneFiles = state.convertFiles.filter((f) => f.status === "done" && f.pathDxf);
    if (doneFiles.length === 0) return alert("완료된 파일이 없습니다.");
    const modeSet = new Set(doneFiles.map((f) => f.convertMode || "dwg2dxf"));
    if (modeSet.size > 1) {
      return alert("변환 방향이 섞여 있어 일괄 다운로드가 불가능합니다.");
    }
    const mode = doneFiles[0].convertMode || "dwg2dxf";
    const kind = mode === "dxf2dwg" ? "dwg" : "dxf";
    try {
      const res = await fetch(`${API_BASE}/convert/bulk-download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_ids: doneFiles.map((f) => f.fileId), kind }),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || "다운로드 실패");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "dxf_bundle.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.message || "다운로드 중 오류가 발생했습니다.");
    }
  };

  $("btnParse").onclick = startParse;

  const parseDownloadBtn = $("btnParseDownload");
  if (parseDownloadBtn) {
    parseDownloadBtn.onclick = () => {
      const file = state.templateFile || state.selectedResult || state.analyzeFiles[0];
      if (!file?.fileId) return alert("파싱 결과를 다운로드할 파일을 선택하세요.");
      window.open(`${API_BASE}/parsing/${file.fileId}/parse1-download`, "_blank");
    };
  }

  $("btnShowDetail").onclick = () => {
    if (!state.templateFile && state.analyzeFiles.length > 0) {
      state.templateFile = state.analyzeFiles[0];
    }
    if (!state.templateFile) {
      alert("템플릿 DXF를 먼저 선택하세요.");
      return;
    }
    const finalize = () => {
      applyTemplateSelections();
      initSmartSelects();
      $("detailSection").style.display = "grid";
    };
    loadParsed(state.templateFile)
      .catch(() => {})
      .finally(finalize);
  };

  $("btnAnalyze").onclick = async () => {
    if (!state.loggedIn) return alert("로그인 후 이용 가능합니다.");
    if (state.analyzeFiles.length === 0) return alert("분석할 DXF 파일을 먼저 업로드하세요.");
    const doneFiles = state.analyzeFiles.filter((f) => f.status === "done");
    if (doneFiles.length === 0) return alert("파싱 완료된 DXF가 없습니다. 먼저 파싱을 완료하세요.");
    const btn = $("btnAnalyze");
    if (btn) btn.classList.add("is-loading");
    if (!state.selectedResult || !doneFiles.includes(state.selectedResult)) {
      state.selectedResult = doneFiles[0];
    }
    const parse2Payload = { selections: { ...state.selectedOptions } };
    for (const f of doneFiles) {
      try {
        await api(`/parsing/${f.fileId}/parse2`, { method: "POST", body: parse2Payload });
      } catch (err) {
        console.warn("parse2 실패", f.fileId, err);
      }
    }
    for (const f of doneFiles) {
      await refreshSemanticSummary(f).catch(() => {});
    }
    renderAiResultView();
    if (state.selectedResult && !state.selectedResult.parsedData) {
      await loadParsed(state.selectedResult);
    }
    if (state.selectedResult && !state.selectedResult.entitiesTable) {
      await loadEntitiesTable(state.selectedResult);
    }
    $("resultSection").style.display = "grid";
    updateResultList(true);
    renderResultView();
    if ($("aiResultSection")) $("aiResultSection").style.display = "grid";
    if (btn) btn.classList.remove("is-loading");
  };

  document.querySelectorAll("[data-detail-tab]").forEach((btn) =>
    btn.addEventListener("click", () => setDetailTab(btn.dataset.detailTab))
  );
}

// 초기화
setTab("home");
updateUserUI();
bindEvents();
updateConvertModeUI();
