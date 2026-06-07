#!/usr/bin/env python3
# ============================================================================
# 校验 vortex-base 的依赖清单是否仍覆盖下游各仓库的声明（依赖漂移检查）。
#
# 做什么：扫描兄弟仓库的 pyproject.toml（project.dependencies +
# optional-dependencies），与 docker/requirements-base.txt（单一真值）逐条比对：
#   [缺失] 某仓库需要、但 base 没装               → 必须在 base 补上（退出码非 0）
#   [过低] base 的版本下限 < 某仓库要求的下限      → 必须抬高 base 下限（退出码非 0）
#   [多余] base 装了、但没有仓库声明              → 仅提示（不报错）
#   [豁免] 已知有意不放进 base 的（pyqlib 等）     → 仅提示
#
# 用法：
#   python scripts/sync-requirements.py                      # 默认扫 ../vortex_{data,qmt,backtest}
#   python scripts/sync-requirements.py ../vortex_data ...   # 指定仓库路径
#   python scripts/sync-requirements.py --quiet              # 只在有「必须修」的漂移时输出
#
# 退出码：0 = 覆盖完整；1 = 存在「缺失/过低」漂移；2 = 用法/环境错误。
# 依赖：Python 3.11+（tomllib；3.10 可 `pip install tomli`）；packaging（通常已随 pip 提供）。
# ============================================================================
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # 3.10 回退
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        sys.exit("需要 Python 3.11+（tomllib）或 `pip install tomli` 才能解析 pyproject.toml")

try:
    from packaging.requirements import Requirement
    from packaging.version import Version
    HAVE_PACKAGING = True
except ModuleNotFoundError:
    HAVE_PACKAGING = False

# 有意「不放进 base」的包：扫到也不算缺失，只提示原因。
# 仅放「某仓确实声明、但有意不进 base」的包。已不被任何仓声明的包（如 qlib/backtrader）
# 不要列在这里——否则将来某仓真声明它时会被误判为「豁免」而非「缺失」。
EXCLUDED = {
    "empyrical-reloaded": "仅 backtest crosscheck 单测对拍用，缺失时该测试自动跳过 → 按需在 backtest 临时装",
    "pytz": "仅随 empyrical-reloaded 的 crosscheck 用 → 同上",
}
DEFAULT_REPOS = ["../vortex_data", "../vortex_qmt", "../vortex_backtest"]


def norm(spec: str) -> str:
    """从一条声明里取规范化分发名：剥掉 extras / 版本操作符 / 环境标记，再小写归一。
    例：'uvicorn[standard]>=0.30' → 'uvicorn'；'pandas>=2.2' → 'pandas'。"""
    name = re.split(r"[\[<>=!~;( ]", spec, 1)[0]
    return name.strip().lower().replace("_", "-").replace(".", "-")


def floor_of(spec: str) -> str | None:
    """从形如 'pandas>=2.2' 的声明里取出版本下限字符串（取不到返回 None）。"""
    if HAVE_PACKAGING:
        try:
            req = Requirement(spec)
            lowers = [s.version for s in req.specifier if s.operator in (">=", "==", "~=")]
            return max(lowers, key=Version) if lowers else None
        except Exception:
            pass
    # 无 packaging 时的简易回退：抓 >= 后面的版本
    for op in (">=", "==", "~="):
        if op in spec:
            tail = spec.split(op, 1)[1]
            return tail.split(",")[0].strip()
    return None


def ge(a: str, b: str) -> bool:
    """a >= b ？有 packaging 用语义版本比较，否则退化为字符串元组比较。"""
    if HAVE_PACKAGING:
        try:
            return Version(a) >= Version(b)
        except Exception:
            pass
    def parts(v: str):
        out = []
        for p in v.replace("-", ".").split("."):
            out.append((int(p), "") if p.isdigit() else (0, p))
        return out
    return parts(a) >= parts(b)


def parse_pyproject(path: Path) -> dict[str, str]:
    """返回 {规范化包名: 原始声明}；同名取下限更高的那条。"""
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    proj = data.get("project", {})
    specs: list[str] = list(proj.get("dependencies", []))
    for grp in proj.get("optional-dependencies", {}).values():
        specs.extend(grp)
    # 构建后端（build-system.requires）也算「base 需要预装」的对象，
    # 否则 hatchling/setuptools 会被误判为 base 多余。
    specs.extend(data.get("build-system", {}).get("requires", []))
    out: dict[str, str] = {}
    for s in specs:
        s = s.strip()
        if not s or s.startswith("#"):
            continue
        key = norm(s)
        if key in out:
            old, new = floor_of(out[key]), floor_of(s)
            if new and (not old or ge(new, old)):
                out[key] = s
        else:
            out[key] = s
    return out


def parse_base(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out[norm(line)] = line
    return out


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    repo_args = [a for a in argv if not a.startswith("-")]
    here = Path(__file__).resolve().parent.parent          # vortex_common/
    base_path = here / "docker" / "requirements-base.txt"
    if not base_path.exists():
        print(f"找不到 base 清单: {base_path}", file=sys.stderr)
        return 2
    base = parse_base(base_path)

    repos = repo_args or DEFAULT_REPOS
    # 汇总各仓库声明：{包名: {下限, 来源仓库列表, 原始声明}}
    wanted: dict[str, dict] = {}
    scanned: list[str] = []
    for r in repos:
        p = (here / r if not Path(r).is_absolute() else Path(r)).resolve()
        pj = p / "pyproject.toml"
        if not pj.exists():
            print(f"!! 跳过（无 pyproject.toml）: {pj}", file=sys.stderr)
            continue
        scanned.append(p.name)
        for key, spec in parse_pyproject(pj).items():
            fl = floor_of(spec)
            ent = wanted.setdefault(key, {"floor": fl, "spec": spec, "repos": []})
            ent["repos"].append(p.name)
            if fl and (not ent["floor"] or ge(fl, ent["floor"])):
                ent["floor"], ent["spec"] = fl, spec

    if not scanned:
        print("没有扫到任何仓库的 pyproject.toml", file=sys.stderr)
        return 2

    missing, too_low, excluded_hits = [], [], []
    for key, ent in sorted(wanted.items()):
        if key in EXCLUDED:
            excluded_hits.append((key, ent, EXCLUDED[key]))
            continue
        if key not in base:
            missing.append((key, ent))
            continue
        bf, rf = floor_of(base[key]), ent["floor"]
        if rf and bf and not ge(bf, rf):
            too_low.append((key, ent, bf))

    unused = sorted(k for k in base if k not in wanted and k not in EXCLUDED)

    problems = bool(missing or too_low)
    if quiet and not problems:
        return 0

    print(f"扫描仓库: {', '.join(scanned)}")
    print(f"base 清单: {base_path}")
    print(f"  base 含 {len(base)} 个包；三仓库共声明 {len(wanted)} 个不同包。")
    print()

    if missing:
        print("❌ [缺失] 仓库需要但 base 没装 —— 请加进 requirements-base.txt：")
        for key, ent in missing:
            print(f"     - {ent['spec']:<28} （{', '.join(ent['repos'])}）")
        print()
    if too_low:
        print("❌ [过低] base 下限低于仓库要求 —— 请抬高 requirements-base.txt 下限：")
        for key, ent, bf in too_low:
            print(f"     - {key}: base>={bf}  <  需要 {ent['spec']}  （{', '.join(ent['repos'])}）")
        print()
    if excluded_hits:
        print("ℹ️  [豁免] 下列包有意不放进 base：")
        for key, ent, why in excluded_hits:
            print(f"     - {key:<20} {why}")
        print()
    if unused:
        print("ℹ️  [多余] base 装了但当前无仓库声明（可能是测试/构建后端，按需保留）：")
        print(f"     {', '.join(unused)}")
        print()

    if problems:
        print("结论：存在必须修复的依赖漂移（见上）。")
        return 1
    print("✅ 结论：base 覆盖三仓库全部声明，版本下限均满足。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
