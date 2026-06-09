#!/usr/bin/env bash
# ============================================================================
# 构建 Vortex 组合镜像 vortex:<tag>：用 deploy/repos/<svc> 里的代码造一个镜像。
#
# 前置：先跑 deploy/pull-code.sh 把各仓拉到 deploy/repos/<svc>（并填好各仓 .env）。
# 本脚本只负责「造镜像」：把 repos/<svc> 的代码装进镜像（--no-deps）。
#   关键：各仓 .env 不进镜像（配置运行时由 compose env_file 注入，改配置不必重建镜像）。
#
# 用法：
#   deploy/build-release.sh                 # 用 deploy/repos/* 构建 vortex:latest
#   deploy/build-release.sh --tag=2026.06.07  # 额外打版本 tag
#   deploy/build-release.sh --no-cache / --push / --keep-stage
#
# 调试覆盖：VORTEX_<SVC>_SRC=/path 用别的本地目录替代 repos/<svc>（SVC=DATA|QMT|BACKTEST|TRADER）
# 环境变量：BASE_IMAGE(默认 vortex-base:latest) IMAGE(默认 vortex:latest) REGISTRY
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"                       # deploy/

MANIFEST="versions.yml"
REPOS="repos"
STAGE=".stage"
BASE_IMAGE="${BASE_IMAGE:-vortex-base:latest}"
IMAGE="${IMAGE:-vortex:latest}"
export DOCKER_BUILDKIT=1

NO_CACHE=""; DO_PUSH=0; EXTRA_TAG=""; KEEP_STAGE=0
for arg in "$@"; do case "$arg" in
  --no-cache)   NO_CACHE="--no-cache" ;;
  --push)       DO_PUSH=1 ;;
  --keep-stage) KEEP_STAGE=1 ;;
  --tag=*)      EXTRA_TAG="${arg#*=}" ;;
  -h|--help)    sed -n '2,18p' "$0"; exit 0 ;;
  *) echo "未知参数: $arg（-h 看用法）" >&2; exit 2 ;;
esac; done

command -v docker >/dev/null || { echo "未找到 docker" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "缺 $MANIFEST" >&2; exit 1; }
docker image inspect "$BASE_IMAGE" >/dev/null 2>&1 || {
  echo "!! 基础镜像 $BASE_IMAGE 不存在。请先：(cd .. && scripts/build-base-image.sh)" >&2; exit 1; }

parse_manifest() {
  awk '
    function flush(){ if(name!=""){ print name } name="" }
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*-[[:space:]]*name:/ { flush(); name=$0; sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/,"",name); gsub(/[[:space:]\r]/,"",name) }
    END{ flush() }
  ' "$MANIFEST"
}

src_for() {   # vortex_data -> $VORTEX_DATA_SRC 或 repos/vortex_data
  local up; up="$(echo "${1#vortex_}" | tr '[:lower:]' '[:upper:]')"
  local v="VORTEX_${up}_SRC"
  echo "${!v:-${REPOS}/$1}"
}
ref_argname() { echo "VORTEX_$(echo "${1#vortex_}" | tr '[:lower:]' '[:upper:]')_REF"; }

# 暂存某仓代码到 .stage/<name>，排除 .env（不进镜像）/.git/.venv 等。返回 ref 标签。
stage_one() {   # name -> echo label
  local name="$1" src dst="${STAGE}/$1" label
  src="$(src_for "$name")"
  rm -rf "$dst"; mkdir -p "$dst"
  if [ -f "${src}/pyproject.toml" ]; then
    tar -C "$src" \
        --exclude='.env' --exclude='.env.*' --exclude=.git --exclude=.venv --exclude=venv \
        --exclude=workspace --exclude=state --exclude=.stage --exclude='__pycache__' \
        --exclude='*.egg-info' --exclude=.pytest_cache --exclude=.DS_Store -cf - . | tar -C "$dst" -xf -
    label="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo local)"
  else
    : > "${dst}/.gitkeep"; label="none"
  fi
  echo "$label"
}

echo ">> 从 ${REPOS}/ 暂存各仓代码（排除 .env，不进镜像）"
BUILD_ARGS=( --build-arg "BASE_IMAGE=${BASE_IMAGE}" )
SUMMARY=""; MISSING=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  src="$(src_for "$name")"
  if [ ! -e "${src}/pyproject.toml" ] && [ -d "${REPOS}" ] && [ ! -d "${src}" ]; then
    # repos/<svc> 不存在且非预留：提示先 pull-code（trader 等预留 ref 为空时允许缺）
    SUMMARY+="   ${name}: <缺，未 pull-code 或预留>\n"
  fi
  label="$(stage_one "$name")"
  BUILD_ARGS+=( --build-arg "$(ref_argname "$name")=${label}" )
  SUMMARY+="   ${name}: ${label}\n"
done < <(parse_manifest)

TAGS=( -t "${REGISTRY:+${REGISTRY}/}${IMAGE}" )
[ -n "$EXTRA_TAG" ] && TAGS+=( -t "${REGISTRY:+${REGISTRY}/}${IMAGE%%:*}:${EXTRA_TAG}" )

echo ">> 各仓版本（镜像 label）："; printf "%b" "$SUMMARY"

# 烤入用的配置 env：从 common config/ 拷进构建上下文（deploy/），供 Dockerfile COPY。
cp ../config/vortex.generated.env ./vortex.generated.env

echo ">> 构建 ${IMAGE}（FROM ${BASE_IMAGE}）"
docker build $NO_CACHE "${BUILD_ARGS[@]}" -f Dockerfile "${TAGS[@]}" .

if [ "$DO_PUSH" = 1 ]; then
  for i in "${!TAGS[@]}"; do [ "${TAGS[$i]}" = "-t" ] && continue; echo ">> 推送 ${TAGS[$i]}"; docker push "${TAGS[$i]}"; done
fi

[ "$KEEP_STAGE" = 1 ] || rm -rf "$STAGE"
docker image ls "${IMAGE%%:*}" --format '   {{.Repository}}:{{.Tag}}  {{.Size}}  ({{.CreatedSince}})' 2>/dev/null || true
echo ">> 完成。启动：docker compose up -d vortex-data （数据）/ docker compose up -d （全栈）"
