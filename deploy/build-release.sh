#!/usr/bin/env bash
# ============================================================================
# 构建 Vortex 组合镜像 vortex:<tag>：按 versions.yml 钉定的各仓 tag 拉代码 → 造一个镜像。
#
# 发版流程：改 versions.yml 里某服务的 ref → 提交 → 跑本脚本 → 得到新镜像。
#
# 用法：
#   deploy/build-release.sh                 # 按 versions.yml 构建 vortex:latest（发版流程）
#   deploy/build-release.sh --tag=2026.06.07  # 额外打一个版本 tag
#   deploy/build-release.sh --no-cache
#   deploy/build-release.sh --push          # 构建后推送（需 docker login；可配 REGISTRY=）
#   deploy/build-release.sh --keep-stage    # 保留 .stage/ 便于排查
#
# 调试（本地源覆盖，不走 git）：把某服务用本地工作区代码（含未提交改动）打进镜像 ——
#   VORTEX_DATA_SRC=../vortex_data deploy/build-release.sh --tag=dev          # 仅 data 用本地
#   VORTEX_DATA_SRC=../vortex_data VORTEX_QMT_SRC=../vortex_qmt \
#   VORTEX_BACKTEST_SRC=../vortex_backtest deploy/build-release.sh --tag=dev  # 全栈用本地
#   未设 *_SRC 的服务仍按 versions.yml 的 tag 从 git 拉。
#
# 环境变量：BASE_IMAGE(默认 vortex-base:latest) IMAGE(默认 vortex:latest) REGISTRY
#           VORTEX_<SVC>_SRC（调试本地源，SVC=DATA|QMT|BACKTEST|TRADER）
# 私有仓由本机 git 凭据/SSH 克隆；凭据不进镜像（代码以 COPY .stage 进镜像）。
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"                       # 切到 deploy/（构建上下文）

MANIFEST="versions.yml"
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
command -v git    >/dev/null || { echo "未找到 git" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "缺少 $MANIFEST" >&2; exit 1; }
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo "!! 基础镜像 $BASE_IMAGE 不存在。请先构建：(cd .. && scripts/build-base-image.sh)" >&2
  exit 1
fi

# ---- 解析 versions.yml（不依赖 PyYAML，按固定结构用 awk）→ TSV: name repo ref submodules ----
parse_manifest() {
  awk '
    function flush(){ if(name!=""){ printf "%s\t%s\t%s\t%s\n", name, repo, ref, subm } name="";repo="";ref="";subm="" }
    /^[[:space:]]*#/        { next }
    /^[[:space:]]*-[[:space:]]*name:/ { flush(); name=$0; sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/,"",name); gsub(/[[:space:]\r]/,"",name); next }
    /^[[:space:]]*repo:/    { repo=$0; sub(/^[[:space:]]*repo:[[:space:]]*/,"",repo); gsub(/[[:space:]\r]/,"",repo); next }
    /^[[:space:]]*ref:/     { ref=$0;  sub(/^[[:space:]]*ref:[[:space:]]*/,"",ref);   gsub(/[[:space:]\r]/,"",ref);  next }
    /^[[:space:]]*submodules:/ { subm=$0; sub(/^[[:space:]]*submodules:[[:space:]]*/,"",subm); gsub(/[[:space:]\r]/,"",subm); next }
    END{ flush() }
  ' "$MANIFEST"
}

ref_argname() {  # vortex_data -> VORTEX_DATA_REF
  echo "VORTEX_$(echo "${1#vortex_}" | tr '[:lower:]' '[:upper:]')_REF"
}

# 调试本地源覆盖：VORTEX_<SVC>_SRC 指本地路径时返回该路径，否则空。
src_for() {
  local up; up="$(echo "${1#vortex_}" | tr '[:lower:]' '[:upper:]')"
  local v="VORTEX_${up}_SRC"; echo "${!v:-}"
}

clone_one() {   # name repo ref submodules
  local name="$1" repo="$2" ref="$3" subm="$4" dst="${STAGE}/$1"
  rm -rf "$dst"; mkdir -p "$dst"
  local src; src="$(src_for "$name")"
  if [ -n "$src" ]; then     # 调试：用本地工作区代码（含未提交改动），不走 git
    echo ">> ${name}: 用本地源 ${src}（调试，不走 git）"
    [ -d "$src" ] || { echo "   本地源目录不存在: $src" >&2; exit 1; }
    tar -C "$src" --exclude=.git --exclude=.venv --exclude=venv --exclude=workspace \
        --exclude=.stage --exclude='__pycache__' --exclude='*.egg-info' \
        --exclude=.pytest_cache --exclude=.DS_Store -cf - . | tar -C "$dst" -xf -
    return 0
  fi
  if [ -z "$ref" ]; then
    echo ">> ${name}: ref 为空 → 预留占位（不纳入本次镜像）"
    : > "${dst}/.gitkeep"
    return 0
  fi
  echo ">> ${name}: 克隆 ${repo} @ ${ref}"
  if ! git clone --depth 1 --branch "$ref" "$repo" "$dst" 2>/dev/null; then
    echo "   (浅克隆指定 ref 失败，回退全克隆再 checkout)"
    rm -rf "$dst"; git clone "$repo" "$dst"; git -C "$dst" checkout "$ref"
  fi
  if [ "$subm" = "true" ]; then
    echo "   检出子模块 ..."
    git -C "$dst" submodule update --init --recursive
  fi
  rm -rf "${dst}/.git"      # 不把 .git 历史塞进构建上下文/镜像
}

echo ">> 解析 ${MANIFEST}"
BUILD_ARGS=( --build-arg "BASE_IMAGE=${BASE_IMAGE}" )
SUMMARY=""
while IFS=$'\t' read -r name repo ref subm; do
  [ -n "$name" ] || continue
  clone_one "$name" "$repo" "$ref" "$subm"
  src="$(src_for "$name")"
  if [ -n "$src" ]; then arg="local"; disp="local:${src}";
  elif [ -z "$ref" ]; then arg="none"; disp="<预留>";
  else arg="$ref"; disp="$ref"; fi
  BUILD_ARGS+=( --build-arg "$(ref_argname "$name")=${arg}" )
  SUMMARY+="   ${name}: ${disp}\n"
done < <(parse_manifest)

# 组装标签
TAGS=( -t "${REGISTRY:+${REGISTRY}/}${IMAGE}" )
[ -n "$EXTRA_TAG" ] && TAGS+=( -t "${REGISTRY:+${REGISTRY}/}${IMAGE%%:*}:${EXTRA_TAG}" )

echo ">> 各仓版本："; printf "%b" "$SUMMARY"
echo ">> 构建 ${IMAGE}（FROM ${BASE_IMAGE}）"
docker build $NO_CACHE "${BUILD_ARGS[@]}" -f Dockerfile "${TAGS[@]}" .

if [ "$DO_PUSH" = 1 ]; then
  for i in "${!TAGS[@]}"; do [ "${TAGS[$i]}" = "-t" ] && continue; echo ">> 推送 ${TAGS[$i]}"; docker push "${TAGS[$i]}"; done
fi

[ "$KEEP_STAGE" = 1 ] || rm -rf "$STAGE"
docker image ls "${IMAGE%%:*}" --format '   {{.Repository}}:{{.Tag}}  {{.Size}}  ({{.CreatedSince}})' 2>/dev/null || true
echo ">> 完成。运行：docker compose -f deploy/docker-compose.yml up -d  （单服务：docker run --rm -p 8765:8765 ${IMAGE} vortexctl data）"
