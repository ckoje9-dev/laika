/**
 * AI 도면 생성 관련 함수
 */
import { state, $, API_BASE } from './state.js';
import { api } from './api.js';

// 생성 관련 상태 확장
state.generateSession = null;      // 현재 세션
state.generateVersions = [];       // 버전 목록
state.currentVersion = null;       // 현재 선택된 버전
state.generateSessions = [];       // 세션 목록
state.generateLoading = false;     // 로딩 상태

/**
 * 세션 목록 조회
 */
export async function loadSessions() {
  const projectId = state.projectId || 'default';
  try {
    const sessions = await api(`/generation/sessions/${projectId}`);
    state.generateSessions = sessions || [];
    renderSessionList();
  } catch (err) {
    console.warn('세션 목록 조회 실패:', err);
    state.generateSessions = [];
  }
}

/**
 * 세션 목록 렌더링
 */
export function renderSessionList() {
  const list = $('generateSessionList');
  if (!list) return;

  if (state.generateSessions.length === 0) {
    list.innerHTML = '<div class="muted">저장된 세션이 없습니다.</div>';
    return;
  }

  list.innerHTML = state.generateSessions.map(s => `
    <button class="btn ghost session-item ${state.generateSession?.id === s.id ? 'active' : ''}" data-session-id="${s.id}">
      <span class="session-title">${s.title || '제목 없음'}</span>
      <span class="session-meta">v${s.version_count} · ${new Date(s.created_at).toLocaleDateString()}</span>
    </button>
  `).join('');

  // 이벤트 바인딩
  list.querySelectorAll('.session-item').forEach(btn => {
    btn.onclick = () => selectSession(btn.dataset.sessionId);
  });
}

/**
 * 세션 선택
 */
export async function selectSession(sessionId) {
  try {
    const versions = await api(`/generation/session/${sessionId}/versions`);
    state.generateVersions = versions || [];
    state.generateSession = state.generateSessions.find(s => s.id === sessionId) || { id: sessionId };

    if (versions.length > 0) {
      state.currentVersion = versions[versions.length - 1]; // 최신 버전
    }

    renderSessionList();
    renderVersionList();
    renderConversationHistory();
    renderGeneratePreview();
  } catch (err) {
    console.error('세션 로드 실패:', err);
    alert('세션을 불러오는데 실패했습니다.');
  }
}

/**
 * 버전 목록 렌더링
 */
export function renderVersionList() {
  const list = $('generateVersionList');
  if (!list) return;

  if (state.generateVersions.length === 0) {
    list.innerHTML = '';
    return;
  }

  list.innerHTML = state.generateVersions.map(v => `
    <button class="btn ghost version-item ${state.currentVersion?.version_number === v.version_number ? 'active' : ''}" data-version="${v.version_number}">
      v${v.version_number}
    </button>
  `).join('');

  // 이벤트 바인딩
  list.querySelectorAll('.version-item').forEach(btn => {
    btn.onclick = () => {
      const vNum = parseInt(btn.dataset.version);
      state.currentVersion = state.generateVersions.find(v => v.version_number === vNum);
      renderVersionList();
      renderGeneratePreview();
    };
  });
}

/**
 * 대화 히스토리 렌더링
 */
export function renderConversationHistory() {
  const container = $('generateHistory');
  if (!container) return;

  if (!state.generateSession?.conversation_history || state.generateSession.conversation_history.length === 0) {
    // 버전에서 히스토리 구성
    if (state.generateVersions.length > 0) {
      const messages = [];
      state.generateVersions.forEach(v => {
        messages.push({ role: 'user', content: v.prompt });
        messages.push({ role: 'assistant', content: `도면을 ${v.version_number === 1 ? '생성' : '수정'}했습니다. (버전 ${v.version_number})` });
      });
      container.innerHTML = messages.map(m => `
        <div class="chat-message ${m.role}">
          <span class="chat-role">${m.role === 'user' ? '사용자' : 'AI'}</span>
          <span class="chat-content">${m.content}</span>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<div class="muted">새 도면을 생성해보세요.</div>';
    }
    return;
  }

  container.innerHTML = state.generateSession.conversation_history.map(m => `
    <div class="chat-message ${m.role}">
      <span class="chat-role">${m.role === 'user' ? '사용자' : 'AI'}</span>
      <span class="chat-content">${m.content}</span>
    </div>
  `).join('');
}

/**
 * 미리보기 렌더링
 */
export function renderGeneratePreview() {
  const container = $('generatePreview');
  if (!container) return;

  if (!state.currentVersion?.dxf_path) {
    container.innerHTML = '<div class="muted" style="display:flex; align-items:center; justify-content:center; height:100%;">도면이 생성되면 여기에 표시됩니다.</div>';
    return;
  }

  // DXF 뷰어 렌더링
  container.innerHTML = '<div id="generateDxfPreview" class="preview-frame"></div>';

  // 뷰어용 가상 파일 객체 생성
  const virtualFile = {
    fileId: 'generated',
    dxfPath: state.currentVersion.dxf_path,
    _dxfContent: null,
  };

  // DXF 파일 로드 후 렌더링
  loadAndRenderDxf(state.currentVersion.dxf_path);
}

/**
 * DXF 파일 로드 및 렌더링
 */
async function loadAndRenderDxf(dxfPath) {
  const previewContainer = $('generateDxfPreview');
  if (!previewContainer) return;

  try {
    // DXF 파일 경로에서 직접 로드
    const response = await fetch(`${API_BASE}/static/${dxfPath.replace(/^.*[\\\/]/, '')}`);
    if (!response.ok) {
      // 파일 ID 기반 다운로드 시도
      const fileId = state.currentVersion?.file_id;
      if (fileId) {
        window.open(`${API_BASE}/generation/download/${fileId}`, '_blank');
      }
      previewContainer.innerHTML = '<div class="muted">미리보기를 로드할 수 없습니다.</div>';
      return;
    }

    const dxfContent = await response.text();

    // three-dxf로 렌더링
    if (window.ThreeDxf && window.DxfParser) {
      const parser = new window.DxfParser();
      const dxf = parser.parseSync(dxfContent);

      const width = previewContainer.clientWidth || 600;
      const height = previewContainer.clientHeight || 400;

      previewContainer.innerHTML = '';
      new window.ThreeDxf.Viewer(dxf, previewContainer, width, height);
    }
  } catch (err) {
    console.warn('DXF 미리보기 로드 실패:', err);
    previewContainer.innerHTML = '<div class="muted">미리보기를 로드할 수 없습니다.</div>';
  }
}

/**
 * 새 도면 생성
 */
export async function startGenerate() {
  const input = $('generatePrompt');
  const prompt = input?.value?.trim();

  if (!prompt) {
    alert('생성할 도면에 대해 설명해주세요.');
    return;
  }

  if (!state.loggedIn) {
    alert('로그인 후 이용 가능합니다.');
    return;
  }

  if (!state.subscribed) {
    alert('구독 후 이용 가능합니다.');
    return;
  }

  const btn = $('btnGenerate');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('is-loading');
  }
  state.generateLoading = true;

  try {
    const projectId = state.projectId || 'default';
    const result = await api('/generation/generate', {
      method: 'POST',
      body: {
        project_id: projectId,
        prompt: prompt,
        session_id: state.generateSession?.id || null,
      },
    });

    // 상태 업데이트
    if (!state.generateSession || state.generateSession.id !== result.session_id) {
      state.generateSession = {
        id: result.session_id,
        title: prompt.slice(0, 50),
      };
    }

    // 버전 추가
    state.generateVersions.push({
      version_number: result.version_number,
      prompt: prompt,
      schema: result.schema,
      validation: result.validation,
      dxf_path: result.dxf_path,
      created_at: new Date().toISOString(),
    });
    state.currentVersion = state.generateVersions[state.generateVersions.length - 1];

    // UI 업데이트
    input.value = '';
    renderVersionList();
    renderConversationHistory();
    renderGeneratePreview();
    loadSessions(); // 세션 목록 새로고침

    // 검증 결과 표시
    if (result.validation && !result.validation.valid) {
      const warnings = result.validation.errors?.join('\n') || '검증 경고가 있습니다.';
      console.warn('검증 결과:', warnings);
    }

  } catch (err) {
    console.error('도면 생성 실패:', err);
    alert(err.message || '도면 생성에 실패했습니다.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('is-loading');
    }
    state.generateLoading = false;
  }
}

/**
 * 도면 수정
 */
export async function modifyDrawing() {
  const input = $('generatePrompt');
  const prompt = input?.value?.trim();

  if (!prompt) {
    alert('수정할 내용을 입력해주세요.');
    return;
  }

  if (!state.generateSession?.id) {
    // 세션이 없으면 새로 생성
    return startGenerate();
  }

  const btn = $('btnModify');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('is-loading');
  }

  try {
    const result = await api('/generation/modify', {
      method: 'POST',
      body: {
        session_id: state.generateSession.id,
        prompt: prompt,
      },
    });

    // 버전 추가
    state.generateVersions.push({
      version_number: result.version_number,
      prompt: prompt,
      schema: result.schema,
      validation: result.validation,
      dxf_path: result.dxf_path,
      created_at: new Date().toISOString(),
    });
    state.currentVersion = state.generateVersions[state.generateVersions.length - 1];

    // UI 업데이트
    input.value = '';
    renderVersionList();
    renderConversationHistory();
    renderGeneratePreview();

  } catch (err) {
    console.error('도면 수정 실패:', err);
    alert(err.message || '도면 수정에 실패했습니다.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('is-loading');
    }
  }
}

/**
 * 새 세션 시작
 */
export function newSession() {
  state.generateSession = null;
  state.generateVersions = [];
  state.currentVersion = null;

  renderSessionList();
  renderVersionList();
  renderConversationHistory();
  renderGeneratePreview();

  const input = $('generatePrompt');
  if (input) input.value = '';
}

/**
 * DXF 다운로드
 */
export function downloadDxf() {
  if (!state.currentVersion?.dxf_path) {
    alert('다운로드할 도면이 없습니다.');
    return;
  }

  const dxfPath = state.currentVersion.dxf_path;
  const filename = dxfPath.split(/[\\\/]/).pop() || 'generated.dxf';

  // 직접 다운로드 링크 생성
  const a = document.createElement('a');
  a.href = `${API_BASE}/generation/download-dxf?path=${encodeURIComponent(dxfPath)}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/**
 * DWG 변환 및 다운로드
 */
export async function convertToDwg() {
  if (!state.currentVersion?.dxf_path) {
    alert('변환할 도면이 없습니다.');
    return;
  }

  const btn = $('btnConvertDwg');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('is-loading');
  }

  try {
    // DXF를 DWG로 변환 요청
    const result = await api('/generation/convert-to-dwg', {
      method: 'POST',
      body: {
        dxf_path: state.currentVersion.dxf_path,
      },
    });

    if (result.dwg_path) {
      const filename = result.dwg_path.split(/[\\\/]/).pop() || 'generated.dwg';
      const a = document.createElement('a');
      a.href = `${API_BASE}/generation/download-dwg?path=${encodeURIComponent(result.dwg_path)}`;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  } catch (err) {
    console.error('DWG 변환 실패:', err);
    alert(err.message || 'DWG 변환에 실패했습니다.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('is-loading');
    }
  }
}

/**
 * 스키마 상세 보기
 */
export function showSchemaDetail() {
  if (!state.currentVersion?.schema) {
    alert('스키마 정보가 없습니다.');
    return;
  }

  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>스키마 상세 (v${state.currentVersion.version_number})</h3>
        <button class="btn ghost modal-close">&times;</button>
      </div>
      <div class="modal-body">
        <pre style="max-height:400px; overflow:auto; background:var(--surface-2); padding:12px; border-radius:8px;">${JSON.stringify(state.currentVersion.schema, null, 2)}</pre>
      </div>
    </div>
  `;

  modal.querySelector('.modal-close').onclick = () => modal.remove();
  modal.onclick = (e) => {
    if (e.target === modal) modal.remove();
  };

  document.body.appendChild(modal);
}

/**
 * 생성 섹션 초기화
 */
export function initGenerateSection() {
  // 구독 상태에 따른 UI 표시
  const lock = $('generateLock');
  const content = $('generateContent');

  if (state.subscribed) {
    if (lock) lock.style.display = 'none';
    if (content) content.style.display = 'grid';
    loadSessions();
  } else {
    if (lock) lock.style.display = 'block';
    if (content) content.style.display = 'none';
  }
}
