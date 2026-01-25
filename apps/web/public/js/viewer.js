/**
 * Three.js DXF 뷰어 관련 함수
 */
import { state, $, API_BASE } from './state.js';

export function loadScriptOnce(url) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = url;
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

export function ensureFontLoader() {
  if (state.fontLoader) return state.fontLoader;
  if (window.THREE && window.THREE.FontLoader) {
    state.fontLoader = new window.THREE.FontLoader();
  }
  return state.fontLoader;
}

export async function ensureFont() {
  if (state.font) return state.font;
  const loader = ensureFontLoader();
  if (!loader) return null;
  if (!state.fontLoading) {
    state.fontLoading = new Promise((resolve, reject) => {
      const candidates = [
        "/vendor/NotoSansKR-Regular.typeface.json",
        "/vendor/helvetiker_regular.typeface.json",
      ];
      const tryLoad = (idx) => {
        if (idx >= candidates.length) {
          reject(new Error("font load failed"));
          return;
        }
        loader.load(
          candidates[idx],
          (font) => resolve(font),
          undefined,
          () => tryLoad(idx + 1)
        );
      };
      tryLoad(0);
    });
  }
  try {
    state.font = await state.fontLoading;
  } catch (e) {
    state.font = null;
  }
  return state.font;
}

export function resolveThreeDxf() {
  return window.ThreeDxf || window.threeDxf || null;
}

export async function ensureThreeDxf() {
  if (state.viewerLib) return state.viewerLib;
  const existing = resolveThreeDxf();
  if (existing) {
    state.viewerLib = existing;
    return existing;
  }
  const urls = [
    "/vendor/three-dxf.js",
    "https://cdn.jsdelivr.net/npm/three-dxf@1.3.1/dist/three-dxf.js",
  ];
  if (!state.viewerLoading) {
    state.viewerLoading = (async () => {
      for (const url of urls) {
        try {
          await loadScriptOnce(url);
          const lib = resolveThreeDxf();
          if (lib) return lib;
        } catch (err) {
          continue;
        }
      }
      return null;
    })();
  }
  state.viewerLib = await state.viewerLoading;
  return state.viewerLib;
}

export function resolveDxfParser() {
  const mod = window.DxfParser || window.DXFParser || null;
  if (!mod) return null;
  return mod.default || mod.DxfParser || mod;
}

export async function ensureDxfParser() {
  if (state.parserLib) return state.parserLib;
  const existing = resolveDxfParser();
  if (existing) {
    state.parserLib = existing;
    return existing;
  }
  const urls = [
    "https://cdn.jsdelivr.net/npm/dxf-parser@1.1.8/dist/dxf-parser.js",
    "https://cdn.jsdelivr.net/npm/dxf-parser@1.1.2/dist/dxf-parser.js",
  ];
  if (!state.parserLoading) {
    state.parserLoading = (async () => {
      for (const url of urls) {
        try {
          await loadScriptOnce(url);
          const ctor = resolveDxfParser();
          if (ctor) return ctor;
        } catch (err) {
          continue;
        }
      }
      return null;
    })();
  }
  state.parserLib = await state.parserLoading;
  return state.parserLib;
}

export async function renderDxfPreview(file, borderBBox) {
  const container = $("dxfPreview");
  if (!container) return;
  container.innerHTML = "";
  if (!file.fileId) {
    container.innerHTML = '<div class="muted" style="padding:12px;">DXF 파일이 준비되면 미리보기를 표시합니다.</div>';
    return;
  }
  const url = `${API_BASE}/parsing/${file.fileId}/download?kind=dxf`;
  const canvas = document.createElement("div");
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  container.appendChild(canvas);
  const loading = document.createElement("div");
  loading.className = "viewer-loading";
  loading.innerHTML = '<span class="throbber"></span>';
  container.appendChild(loading);
  const threeDxf = await ensureThreeDxf();
  const Parser = await ensureDxfParser();
  const font = await ensureFont();
  if (!threeDxf || !Parser) {
    container.innerHTML =
      '<div class="muted" style="padding:12px;">뷰어/파서 스크립트를 불러오지 못했습니다. <a href="' +
      url +
      '" target="_blank">파일을 다운로드</a> 후 확인하세요.</div>';
    return;
  }

  let text;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("DXF 요청 실패");
    text = await res.text();
  } catch (err) {
    container.innerHTML =
      '<div class="muted" style="padding:12px;">DXF 다운로드 실패: ' +
      (err?.message || err?.toString?.() || "알 수 없는 오류") +
      '</div>';
    return;
  }

  let parsed;
  try {
    const parser = new Parser();
    parsed = parser.parseSync(text);
  } catch (err) {
    container.innerHTML =
      '<div class="muted" style="padding:12px;">DXF 파싱 실패: ' +
      (err?.message || err?.toString?.() || "알 수 없는 오류") +
      '</div>';
    return;
  }

  let capturedCamera = null;
  const Ortho = window.THREE?.OrthographicCamera;
  if (Ortho) {
    window.THREE.OrthographicCamera = function (...args) {
      const cam = new Ortho(...args);
      capturedCamera = cam;
      return cam;
    };
    window.THREE.OrthographicCamera.prototype = Ortho.prototype;
  }
  try {
    const width = container.clientWidth || container.offsetWidth || 600;
    const height = container.clientHeight || container.offsetHeight || 340;
    const viewer = new threeDxf.Viewer(parsed, canvas, width, height, font || undefined);
    if (viewer.render) viewer.render();
    if (capturedCamera && borderBBox) {
      const xmin = Number(borderBBox.xmin);
      const ymin = Number(borderBBox.ymin);
      const xmax = Number(borderBBox.xmax);
      const ymax = Number(borderBBox.ymax);
      if ([xmin, ymin, xmax, ymax].every(Number.isFinite)) {
        const pad = 0.05;
        let viewW = Math.max(1, (xmax - xmin) * (1 + pad));
        let viewH = Math.max(1, (ymax - ymin) * (1 + pad));
        const aspect = width / height;
        if (aspect > viewW / viewH) {
          viewW = viewH * aspect;
        } else {
          viewH = viewW / aspect;
        }
        capturedCamera.left = -viewW / 2;
        capturedCamera.right = viewW / 2;
        capturedCamera.top = viewH / 2;
        capturedCamera.bottom = -viewH / 2;
        capturedCamera.position.x = (xmin + xmax) / 2;
        capturedCamera.position.y = (ymin + ymax) / 2;
        capturedCamera.position.z = 10;
        capturedCamera.updateProjectionMatrix();
        capturedCamera.lookAt(capturedCamera.position.x, capturedCamera.position.y, 0);
        if (viewer.render) viewer.render();
      }
    }
    window.addEventListener("resize", () => viewer.resize && viewer.resize(container.clientWidth, container.clientHeight));
    loading.remove();
  } catch (err) {
    container.innerHTML =
      '<div class="muted" style="padding:12px;">뷰어 렌더링 실패: ' +
      (err?.message || err?.toString?.() || "알 수 없는 오류") +
      '</div>';
  } finally {
    if (Ortho) {
      window.THREE.OrthographicCamera = Ortho;
    }
  }
}
