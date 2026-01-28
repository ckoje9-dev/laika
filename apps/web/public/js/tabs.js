/**
 * 탭 네비게이션
 */
import { state, $ } from './state.js';

export function setTab(tab) {
  if (tab === "analyze" && !state.loggedIn) {
    alert("AI 도면 분석은 로그인 후 이용 가능합니다.");
    tab = "login";
  }
  if (tab === "generate" && (!state.loggedIn || !state.subscribed)) {
    if (!state.loggedIn) {
      alert("AI 도면 생성은 로그인 후 이용 가능합니다.");
      tab = "login";
    } else {
      alert("AI 도면 생성은 구독 후 이용 가능합니다.");
      tab = "generate";
    }
  }
  state.activeTab = tab;
  document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === tab));
  document.querySelectorAll("section").forEach((sec) => sec.classList.toggle("active", sec.id === tab));
  if ($("analyzeLock")) $("analyzeLock").style.display = state.loggedIn ? "none" : "inline-flex";
  if ($("generateLock")) $("generateLock").style.display = state.subscribed ? "none" : "inline-flex";
  if ($("generateContent")) $("generateContent").style.display = state.subscribed ? "grid" : "none";

  // AI 도면 생성 탭 진입 시 템플릿 목록 새로고침
  if (tab === "generate" && state.subscribed) {
    import('./generate.js').then(mod => mod.loadTemplateFiles()).catch(() => {});
  }
}

export function setDetailTab(tab) {
  document.querySelectorAll("[data-detail-tab]").forEach((btn) =>
    btn.classList.toggle("active", btn.dataset.detailTab === tab)
  );
  document.querySelectorAll(".tab-panel").forEach((panel) =>
    panel.classList.toggle("active", panel.id === `panel-${tab}`)
  );
}
