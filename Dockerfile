# AI_ROI 이미지 초안 (#207) — Python 3.12 파이프라인 + 빌드된 대시보드(Node 22).
#
# 범위: **빌드까지.** docker-compose(파이프라인 → results/ 볼륨 → 대시보드)는 다음
# 스프린트(#231)다. 완료 조건은 "서브모듈 없는 클론에서 `docker build` 성공" 이다.
#
#   docker build -t airoi .
#   docker run --rm -p 3001:3001 airoi                         # 대시보드 → http://localhost:3001
#   docker run --rm airoi python -m src.measurement.publish     # 파이프라인 명령 예
#
# ★ Plan/ 은 이미지에 들어가지 않는다(.dockerignore). private 기획 문서를 이미지에 굽지 않고,
#   Plan 이 있는 클론과 없는 클론이 같은 이미지를 만든다. 대시보드 토큰은 커밋된
#   dashboard/src/styles/tokens.generated.css 를 쓴다(DR-207-plan-free-tokens).
# ★ Python 3.12 — 전체 파이프라인의 지원 런타임이다(DR-207-python-runtime). 고정 의존성
#   numpy 2.5.4 · scipy 1.18.1 · shap 0.54.1 이 Requires-Python >=3.12 다.
# ★ 베이스 이미지는 태그 + 다이제스트로 고정한다(NFR-001 재현성 — CI 액션을 SHA 로 고정하는 것과
#   같은 이유). 갱신할 때 태그와 다이제스트를 함께 바꾼다.

# ── 1단계: 대시보드 빌드 ──────────────────────────────────────────────────────────
# Node 22 = .github/workflows/dashboard.yml 과 같은 메이저.
FROM node:22.23.4-trixie-slim@sha256:8eb619e402eaede1748a3c8173bffab391592812e85136452f781741c7242ddf AS dashboard
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
# prebuild 가 tokens-prebuild.mjs 를 돈다 — ../Plan/DESIGN.md 가 없으므로 "tokens:check 미실행"
# 을 출력하고 커밋된 생성물로 빌드한다. 생성물이 없으면 여기서 실패한다.
RUN npm run build \
 && npm prune --omit=dev --no-audit --no-fund

# ── 2단계: 런타임 ───────────────────────────────────────────────────────────────
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# 런타임 의존성만(requirements.txt). 개발 의존성(jsonschema · referencing)은 테스트용이라 넣지 않는다.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 선택 — 딥러닝(Churn GRU, requirements-ml.txt). 기본은 넣지 않는다.
# PyPI 의 Linux torch 는 CUDA 패키지를 끌고 와 수 GB 가 된다. 전체 시스템이 CPU 에서 돈다(NFR-03)
# 이므로 켤 때는 PyTorch CPU 인덱스에서 받는다: docker build --build-arg WITH_TORCH=1 .
ARG WITH_TORCH=0
COPY requirements-ml.txt ./
RUN if [ "$WITH_TORCH" = "1" ]; then \
      pip install -r requirements-ml.txt --index-url https://download.pytorch.org/whl/cpu; \
    fi

# 비루트로 돈다. 소스는 root 소유(읽기 전용)로 두고, 쓰는 자리만 app 에게 준다.
RUN useradd --create-home --uid 1000 app

# 대시보드 런타임 — node 실행 파일 + 빌드 산출물(.next) + 운영 의존성만 남긴 node_modules.
COPY --from=dashboard /usr/local/bin/node /usr/local/bin/node

COPY . .
COPY --from=dashboard /app/dashboard/node_modules ./dashboard/node_modules
# next start 가 .next/ 아래에 캐시를 쓴다.
COPY --from=dashboard --chown=app:app /app/dashboard/.next ./dashboard/.next

# 결과·데이터 디렉터리를 미리 만든다(SYS-001 "필요한 volume/directories 자동 생성").
# compose 가 볼륨을 붙일 자리다. /app 자체도 app 소유로 둔다 — 게시(publish)가 results/ 옆에
# results.staging/ 을 만들고 바꿔치기하기 때문이다(원자적 게시). 파일은 root 소유 그대로다.
RUN mkdir -p data results models \
 && chown app:app /app data results models
USER app

# 컨테이너 루프백에 묶이면 -p 포트 매핑이 닿지 않는다. 로컬 기본(127.0.0.1)은 그대로다.
ENV AIROI_DASHBOARD_HOST=0.0.0.0 \
    AIROI_RESULTS_DIR=/app/results
EXPOSE 3001

CMD ["node", "dashboard/scripts/serve.mjs", "start"]
