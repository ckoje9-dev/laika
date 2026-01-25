/**
 * 인증 관련 함수
 */
import { state, $ } from './state.js';
import { setTab } from './tabs.js';

export function updateUserUI() {
  $("userBadge").textContent = state.loggedIn
    ? `${state.user.id} · ${state.subscribed ? "구독" : "회원"}${state.user.role === "admin" ? " · 관리자" : ""}`
    : "게스트 · 비로그인";
  $("btnLogin").textContent = state.loggedIn ? "로그아웃" : "로그인";
  $("btnSignup").textContent = state.loggedIn ? "계정" : "회원가입";
  if ($("generateLock")) $("generateLock").style.display = state.subscribed ? "none" : "inline-flex";
  if ($("analyzeLock")) $("analyzeLock").style.display = state.loggedIn ? "none" : "inline-flex";
}

export function doLogout() {
  state.loggedIn = false;
  state.subscribed = false;
  state.user = null;
  updateUserUI();
  setTab("home");
}

export function doLogin(id, pwd) {
  const found = state.users.find((u) => u.id === id && u.pwd === pwd);
  if (!found) return alert("아이디 또는 비밀번호를 확인하세요.");
  state.loggedIn = true;
  state.user = { ...found };
  state.subscribed = !!found.subscribed;
  updateUserUI();
  setTab("home");
}

export function doSignup(id, pwd, pwd2) {
  if (!id || !pwd || !pwd2) return alert("모든 항목을 입력하세요.");
  if (pwd !== pwd2) return alert("비밀번호가 일치하지 않습니다.");
  if (state.users.find((u) => u.id === id)) return alert("이미 존재하는 아이디입니다.");
  state.users.push({ id, pwd, role: "user", subscribed: false });
  alert("가입이 완료되었습니다. 로그인해주세요.");
  setTab("login");
}
