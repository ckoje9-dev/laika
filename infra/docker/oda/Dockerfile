# ODA File Converter container build (offline, deb provided locally)
FROM ubuntu:22.04

ARG DEB_PATH=tools/oda/ODAFileConverter_QT6_lnxX64_8.3dll_26.10.deb

WORKDIR /workspace

# 필수 도구 및 최소 런타임 라이브러리 설치 (헤드리스 실행용)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      libgl1 \
      libfontconfig1 \
      libfreetype6 \
      libxkbcommon0 \
      libdbus-1-3 \
      libopengl0 \
      libegl1 \
      qt6-base-dev \
      libjpeg62-turbo \
      libtiff5 \
      libxcursor1 \
      xvfb \
      libxcb1 \
      libxcb-shm0 \
      libxcb-render0 \
      libxcb-shape0 \
      libxcb-xfixes0 \
      libxcb-xinerama0 \
      libxcb-icccm4 \
      libxcb-image0 \
      libxcb-keysyms1 \
      libxcb-glx0 \
      libxcb-sync1 \
      libxcb-render-util0 \
      libxcb-xkb1 \
      libxcb-cursor0 \
      libxcb-util1 \
      libxcb-randr0 \
      libx11-xcb1 && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /tmp/runtime-root && chmod 700 /tmp/runtime-root

# 호스트에서 제공한 deb 복사 후 설치
COPY ${DEB_PATH} /tmp/oda.deb
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/oda.deb && \
    rm -rf /var/lib/apt/lists/* /tmp/oda.deb

# 런타임 디렉토리 (xvfb/xcb 경고 방지)
ENV XDG_RUNTIME_DIR=/tmp/runtime-root

# xvfb-run으로 헤드리스 실행
ENTRYPOINT ["/usr/bin/xvfb-run", "--auto-servernum", "--server-args=-screen 0 1024x768x24", "/usr/bin/ODAFileConverter"]
