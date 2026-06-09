#!/usr/bin/env bash
# ============================================================================
# 拉/更新各服务仓代码到 deploy/repos/<svc>（持久），并首次从各仓 .env.example 种出 .env。
#
# 设计：配置归各仓所有——各仓提交 .env.example（模板），gitignore 真 .env（含密钥，不入库）。
#   本脚本把各仓按 versions.yml 的 ref 拉到 deploy/repos/<svc>，并首次从该仓 .env.example 种一份
#   .env 供你填密钥。.env 被各仓 gitignore，不入库；后续 pull-code 更新（git fetch/checkout）也
#   不会动这份被忽略的 .env，你的编辑保留。common 自己不存任何配置值。
#
# 用法：
#   deploy/pull-code.sh            # 拉/更新全部仓
#   deploy/pull-code.sh data qmt   # 只拉指定服务
#
# 之后：编辑 deploy/repos/<svc>/.env → deploy/build-release.sh → docker compose up -d
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"          # deploy/

MANIFEST="versions.yml"
REPOS="repos"

command -v git >/dev/null || { echo "未找到 git" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "缺 $MANIFEST" >&2; exit 1; }

want=("$@")   # 可选：只拉这些服务名（vortex_ 前缀可省略）
wanted() {    # name -> 是否在 want 列表（空列表=全要）
  [ "${#want[@]}" -eq 0 ] && return 0
  local n="$1"; local w
  for w in "${want[@]}"; do [ "$w" = "$n" ] || [ "vortex_$w" = "$n" ] && return 0; done
  return 1
}

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

mkdir -p "$REPOS"
NEED_FILL=()
while IFS=$'\t' read -r name repo ref subm; do
  [ -n "$name" ] || continue
  wanted "$name" || continue
  dst="${REPOS}/${name}"
  if [ -z "$ref" ]; then
    echo ">> ${name}: ref 为空 → 预留，跳过"
    continue
  fi
  if [ -d "${dst}/.git" ]; then
    echo ">> ${name}: 更新到 ${ref}"
    git -C "$dst" fetch --depth 1 origin "$ref" 2>/dev/null || git -C "$dst" fetch origin
    git -C "$dst" checkout -q "$ref" 2>/dev/null || git -C "$dst" checkout -q FETCH_HEAD
  else
    echo ">> ${name}: 克隆 ${repo} @ ${ref}"
    git clone --depth 1 --branch "$ref" "$repo" "$dst" 2>/dev/null \
      || { rm -rf "$dst"; git clone "$repo" "$dst"; git -C "$dst" checkout "$ref"; }
  fi
  [ "$subm" = "true" ] && git -C "$dst" submodule update --init --recursive || true

  # 配置：各仓 .env 被 gitignore（含密钥、不入库）。首次从 .env.example 种一份供你填；
  # 之后保留你的编辑（.env 被忽略，git fetch/checkout 不会动它）。
  if [ -f "${dst}/.env" ]; then
    echo "   .env 已存在，保留你的编辑（不覆盖）"
  elif [ -f "${dst}/.env.example" ]; then
    cp "${dst}/.env.example" "${dst}/.env"
    echo "   已从 .env.example 创建 .env —— 去填密钥（.env 被本仓 gitignore，不入库）"
  else
    echo "   !! ${dst} 没有 .env.example——该仓还没提供配置模板（见迁移指南 §5）"
    NEED_FILL+=("$name")
  fi
done < <(parse_manifest)

echo ""
echo ">> 代码已就位于 deploy/repos/。下一步：编辑各仓 .env 填配置（URL 已预填，补 token/凭证）："
for d in "$REPOS"/*/; do [ -f "${d}.env" ] && echo "     ${d}.env"; done
[ "${#NEED_FILL[@]}" -gt 0 ] && echo ">> 注意：${NEED_FILL[*]} 还没提供 .env.example（按迁移指南 §5 补）。"
echo ">> 填完即可：deploy/build-release.sh && docker compose up -d"
