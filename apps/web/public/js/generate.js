/**
 * AI 도면 생성 관련 함수
 */
import { state, $, API_BASE } from './state.js';
import { api } from './api.js';

// 생성 관련 상태
state.generateLoading = false;
state.templateFiles = [];         // 템플릿 파일 목록
state.selectedTemplateId = null;  // 선택된 템플릿 파일 ID
state.conversationHistory = [];   // 대화 히스토리
state.currentSchema = null;       // 현재 스키마
state.currentDxfPath = null;      // 현재 DXF 경로

/**
 * 템플릿 파일 목록 조회
 */
export async function loadTemplateFiles() {
  const projectId = state.projectId || 'default';
  try {
    const files = await api(`/generation/reference-files/${projectId}`);
    state.templateFiles = (files || []).filter(f => f.has_parsed);
    renderTemplateSelect();
  } catch (err) {
    console.warn('템플릿 파일 목록 조회 실패:', err);
    state.templateFiles = [];
    renderTemplateSelect();
  }
}

/**
 * 템플릿 드롭다운 렌더링
 */
function renderTemplateSelect() {
  const select = $('templateSelect');
  if (!select) return;

  // 옵션 초기화
  select.innerHTML = '<option value="">선택 파일 없음</option>';

  state.templateFiles.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.file_id;
    opt.textContent = f.filename || f.file_id.slice(0, 8);
    if (state.selectedTemplateId === f.file_id) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });

  // 이벤트 바인딩
  select.onchange = () => {
    state.selectedTemplateId = select.value || null;
  };
}

/**
 * 대화 히스토리 렌더링
 */
export function renderConversationHistory() {
  const container = $('generateHistory');
  if (!container) return;

  if (state.conversationHistory.length === 0) {
    container.innerHTML = '<div class="muted">새 도면을 생성해보세요.</div>';
    return;
  }

  container.innerHTML = state.conversationHistory.map(m => `
    <div class="chat-message ${m.role}">
      <span class="chat-role">${m.role === 'user' ? '사용자' : 'AI'}</span>
      <span class="chat-content">${m.content}</span>
    </div>
  `).join('');

  // 스크롤 맨 아래로
  container.scrollTop = container.scrollHeight;
}

/**
 * 미리보기 렌더링
 */
export function renderGeneratePreview() {
  const container = $('generatePreview');
  if (!container) return;

  if (!state.currentDxfPath) {
    container.innerHTML = '<div class="muted" style="display:flex; align-items:center; justify-content:center; height:100%;">도면이 생성되면 여기에 표시됩니다.</div>';
    return;
  }

  // DXF 뷰어 렌더링
  container.innerHTML = '<div id="generateDxfPreview" class="preview-frame"></div>';
  loadAndRenderDxf(state.currentDxfPath);
}

/**
 * DXF 파일 로드 및 렌더링
 */
async function loadAndRenderDxf(dxfPath) {
  const previewContainer = $('generateDxfPreview');
  if (!previewContainer) return;

  try {
    const response = await fetch(`${API_BASE}/static/${dxfPath.replace(/^.*[\\\/]/, '')}`);
    if (!response.ok) {
      previewContainer.innerHTML = '<div class="muted">미리보기를 로드할 수 없습니다.</div>';
      return;
    }

    const dxfContent = await response.text();

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
 * 도면 생성
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

  // 대화에 사용자 메시지 추가
  state.conversationHistory.push({ role: 'user', content: prompt });
  renderConversationHistory();

  try {
    const projectId = state.projectId || 'default';
    const body = {
      project_id: projectId,
      prompt: prompt,
      conversation_history: state.conversationHistory.slice(0, -1), // 현재 메시지 제외한 히스토리
    };

    // 템플릿이 선택되어 있으면 추가
    if (state.selectedTemplateId) {
      body.template_file_id = state.selectedTemplateId;
    }

    const result = await api('/generation/generate', {
      method: 'POST',
      body,
    });

    // 상태 업데이트
    state.currentSchema = result.schema;
    state.currentDxfPath = result.dxf_path;

    // AI 응답 추가
    state.conversationHistory.push({
      role: 'assistant',
      content: result.message || '도면을 생성했습니다.'
    });

    // UI 업데이트
    input.value = '';
    renderConversationHistory();
    renderGeneratePreview();

    // 검증 결과 표시
    if (result.validation && !result.validation.valid) {
      const warnings = result.validation.errors?.join('\n') || '검증 경고가 있습니다.';
      console.warn('검증 결과:', warnings);
    }

  } catch (err) {
    console.error('도면 생성 실패:', err);
    // 실패 시 사용자 메시지 제거
    state.conversationHistory.pop();
    renderConversationHistory();
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
 * 대화 초기화
 */
export function clearConversation() {
  state.conversationHistory = [];
  state.currentSchema = null;
  state.currentDxfPath = null;
  renderConversationHistory();
  renderGeneratePreview();

  const input = $('generatePrompt');
  if (input) input.value = '';
}

/**
 * DXF 다운로드
 */
export function downloadDxf() {
  if (!state.currentDxfPath) {
    alert('다운로드할 도면이 없습니다.');
    return;
  }

  const dxfPath = state.currentDxfPath;
  const filename = dxfPath.split(/[\\\/]/).pop() || 'generated.dxf';

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
  if (!state.currentDxfPath) {
    alert('변환할 도면이 없습니다.');
    return;
  }

  const btn = $('btnConvertDwg');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('is-loading');
  }

  try {
    const result = await api('/generation/convert-to-dwg', {
      method: 'POST',
      body: {
        dxf_path: state.currentDxfPath,
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
  if (!state.currentSchema) {
    alert('스키마 정보가 없습니다.');
    return;
  }

  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>스키마 상세</h3>
        <button class="btn ghost modal-close">&times;</button>
      </div>
      <div class="modal-body">
        <pre style="max-height:400px; overflow:auto; background:var(--surface-2); padding:12px; border-radius:8px;">${JSON.stringify(state.currentSchema, null, 2)}</pre>
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
  const lock = $('generateLock');
  const content = $('generateContent');

  if (state.subscribed) {
    if (lock) lock.style.display = 'none';
    if (content) content.style.display = 'grid';
    loadTemplateFiles();
  } else {
    if (lock) lock.style.display = 'block';
    if (content) content.style.display = 'none';
  }
}
