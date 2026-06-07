#!/usr/bin/env bash
# ============================================================================
# 构建 vortex 统一基础镜像 vortex-base（全家共用的第三方依赖底座）。
#
# 依赖只在这一步下载一次，冻结进镜像。之后下游各仓库的应用镜像
# FROM vortex-base，只叠加代码（pip install --no-deps .），改代码秒级重建。
#
# 用法：
#   scripts/build-base-image.sh                 # 构建 vortex-base:latest
#   scripts/build-base-image.sh base            # 同上（兼容写法，base 是唯一目标）
#   scripts/build-base-image.sh --no-cache      # 不用缓存重建
#   scripts/build-base-image.sh --tag v0.1.0    # 额外打一个版本 tag
#   scripts/build-base-image.sh --push          # 构建后推送到镜像仓库（需已 docker login）
#   scripts/build-base-image.sh --platform linux/amd64,linux/arm64  # 多架构（需 buildx，含 --push）
#
# 环境变量：
#   BASE_IMAGE   产出镜像名:tag（默认 vortex-base:latest）
#   BASE_FROM    底座镜像（默认 python:3.12-slim；离线时自动兜底，见下）
#   REGISTRY     推送前缀，如 ghcr.io/zyukyunman（配合 --push）
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."          # 切到仓库根（vortex_common/）
DOCKER_DIR="docker"              # Dockerfile.base 与 requirements-base.txt 所在（即构建上下文）

BASE_IMAGE="${BASE_IMAGE:-vortex-base:latest}"
export DOCKER_BUILDKIT=1

NO_CACHE=""
DO_PUSH=0
EXTRA_TAG=""
PLATFORM=""
for arg in "$@"; do
  case "$arg" in
    base)            : ;;                       # 唯一构建目标，接受但忽略
    --no-cache)      NO_CACHE="--no-cache" ;;
    --push)          DO_PUSH=1 ;;
    --tag=*)         EXTRA_TAG="${arg#*=}" ;;
    --tag)           echo "用法：--tag=<标签>（如 --tag=v0.1.0）" >&2; exit 2 ;;
    --platform=*)    PLATFORM="${arg#*=}" ;;
    --platform)      echo "用法：--platform=<平台>（如 --platform=linux/amd64,linux/arm64）" >&2; exit 2 ;;
    -h|--help)       sed -n '2,30p' "$0"; exit 0 ;;
    v*|*.*.*)        EXTRA_TAG="$arg" ;;         # 容忍直接写 v0.1.0
    *) echo "未知参数: ${arg} （-h 看用法）" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null || { echo "未找到 docker" >&2; exit 1; }

[ -f "${DOCKER_DIR}/Dockerfile.base" ]      || { echo "缺少 ${DOCKER_DIR}/Dockerfile.base" >&2; exit 1; }
[ -f "${DOCKER_DIR}/requirements-base.txt" ] || { echo "缺少 ${DOCKER_DIR}/requirements-base.txt" >&2; exit 1; }

# 选底座镜像：默认官方 python:3.12-slim；Docker Hub 不可达且本地无该镜像时，
# 自动复用「本地已有、含 Python 的镜像」作底座（完全离线，不去 Hub 拉取）。
resolve_base_from() {
  if [ -n "${BASE_FROM:-}" ]; then echo "$BASE_FROM"; return; fi
  if docker image inspect python:3.12-slim >/dev/null 2>&1; then
    echo "python:3.12-slim"; return
  fi
  # 本地没有官方底座：尝试联网快速探测 Hub 是否可达（3s 超时）。
  if docker pull -q python:3.12-slim >/dev/null 2>&1; then
    echo "python:3.12-slim"; return
  fi
  # 离线兜底：找一个本地已有、含 Python 的镜像当底座。
  for cand in vortex-base:latest vortex-data-base:latest python:3.12-slim python:3.11-slim; do
    if docker image inspect "$cand" >/dev/null 2>&1; then
      echo ">> Docker Hub 不可达，离线复用本地底座: ${cand}" >&2
      echo "$cand"; return
    fi
  done
  echo "python:3.12-slim"   # 最终兜底（在线环境会去 Hub 拉取）
}

# 组装 -t 标签数组（latest + 可选版本 tag；可选 REGISTRY 前缀）
TAGS=("-t" "${REGISTRY:+${REGISTRY}/}${BASE_IMAGE}")
if [ -n "$EXTRA_TAG" ]; then
  repo="${BASE_IMAGE%%:*}"
  TAGS+=("-t" "${REGISTRY:+${REGISTRY}/}${repo}:${EXTRA_TAG}")
fi

BASE_FROM_RESOLVED="$(resolve_base_from)"
echo ">> 构建基础镜像 ${BASE_IMAGE}（底座 ${BASE_FROM_RESOLVED}；依赖只下这一次，走 PyPI）"

if [ -n "$PLATFORM" ]; then
  # 多架构：必须用 buildx。多架构镜像无法 --load 到本地，跨架构通常配合 --push。
  echo ">> 多架构构建：${PLATFORM}"
  OUTPUT="--load"
  [ "$DO_PUSH" = 1 ] && OUTPUT="--push"
  if [ "$DO_PUSH" = 0 ] && printf '%s' "$PLATFORM" | grep -q ','; then
    echo "!! 多架构（多个平台）无法 --load 到本地，请加 --push 推送到仓库。" >&2
    exit 2
  fi
  docker buildx build $NO_CACHE \
    --platform "$PLATFORM" \
    --build-arg BASE_FROM="$BASE_FROM_RESOLVED" \
    -f "${DOCKER_DIR}/Dockerfile.base" \
    "${TAGS[@]}" $OUTPUT "$DOCKER_DIR"
else
  docker build $NO_CACHE \
    --build-arg BASE_FROM="$BASE_FROM_RESOLVED" \
    -f "${DOCKER_DIR}/Dockerfile.base" \
    "${TAGS[@]}" "$DOCKER_DIR"
  if [ "$DO_PUSH" = 1 ]; then
    for i in "${!TAGS[@]}"; do
      [ "${TAGS[$i]}" = "-t" ] && continue
      echo ">> 推送 ${TAGS[$i]}"
      docker push "${TAGS[$i]}"
    done
  fi
fi

echo ">> 镜像："
docker image ls "${BASE_IMAGE%%:*}" --format '   {{.Repository}}:{{.Tag}}  {{.Size}}  ({{.CreatedSince}})' 2>/dev/null || true
echo ">> 完成。下游仓库可 FROM ${BASE_IMAGE} 构建应用镜像（见 README）。"
