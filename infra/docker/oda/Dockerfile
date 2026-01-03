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
      libjpeg-turbo8 \
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

# SHX 폰트 배치 (빌드 전 infra/docker/oda/fonts/whgdtxt.shx 를 준비하세요)
RUN mkdir -p /usr/share/fonts/oda-shx /usr/share/opendesign/Fonts /usr/local/share/fonts/oda-shx
COPY infra/docker/oda/fonts/* /usr/share/fonts/oda-shx/
COPY infra/docker/oda/fonts/* /usr/share/opendesign/Fonts/
COPY infra/docker/oda/fonts/* /usr/local/share/fonts/oda-shx/
RUN fc-cache -fv

# 런타임 디렉토리 (xvfb/xcb 경고 방지)
ENV XDG_RUNTIME_DIR=/tmp/runtime-root
ENV ODACONV_FONTPATH="/usr/share/fonts/oda-shx:/usr/share/opendesign/Fonts:/usr/local/share/fonts/oda-shx"

# Xvfb 수동 구동 후 ODAFileConverter 실행 스크립트
RUN cat >/usr/local/bin/oda-entrypoint.sh <<'EOF' \
 && chmod +x /usr/local/bin/oda-entrypoint.sh
#!/bin/sh
set -e
# Xauthority가 없어서 실패하는 이슈가 있어 -auth 옵션을 제거
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp &
export DISPLAY=:99
exec /usr/bin/ODAFileConverter "$@"
EOF

ENTRYPOINT ["/usr/local/bin/oda-entrypoint.sh"]
