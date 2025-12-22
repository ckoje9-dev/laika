# ODA File Converter container build (offline, deb provided locally)
FROM ubuntu:22.04

ARG DEB_PATH=tools/oda/ODAFileConverter_QT6_lnxX64_8.3dll_26.10.deb

WORKDIR /workspace

# 필수 도구 및 라이브러리 설치
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      libgl1 \
      libxrender1 \
      libxext6 \
      libfontconfig1 \
      libfreetype6 && \
    rm -rf /var/lib/apt/lists/*

# 호스트에서 제공한 deb 복사 후 설치
COPY ${DEB_PATH} /tmp/oda.deb
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/oda.deb && \
    rm -rf /var/lib/apt/lists/* /tmp/oda.deb

# 기본 실행 파일 위치: /usr/bin/ODAFileConverter (deb 설치 기준)
ENTRYPOINT ["/usr/bin/ODAFileConverter"]
