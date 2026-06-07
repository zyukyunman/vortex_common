# deploy/ —— Vortex 组合镜像：发布与部署

一个镜像装下全部服务代码（各仓按 [`versions.yml`](versions.yml) 钉定的 tag），
用户拿到后一条命令即可使用全部功能。架构决策见 [ADR-001](../docs/adr/ADR-001-deployment-architecture.md)。

## 是什么

| 文件 | 作用 |
|------|------|
| `versions.yml` | 各仓版本清单（每仓库各自 tag）。**改 ref 即发版。** |
| `build-release.sh` | 读清单 → 按 tag 浅克隆各仓 → 构建 `vortex:<tag>`（FROM `vortex-base`），各仓 ref 烙进镜像 label |
| `Dockerfile` | 组合镜像：装入各服务代码（`--no-deps`）+ `vortexctl` 启动器，非 root 运行 |
| `bin/vortexctl` | 统一启动器：`vortexctl <svc>`（前台单服务）/ `list`（查看已装入服务） |
| `docker-compose.yml` | 顶层编排：同一镜像、每服务一容器（主部署形态） |

## 发版（每仓库各自 tag）

```bash
# 1) 改 versions.yml 里某服务的 ref（如 vortex_data: v0.2.0）
# 2) 提交——这次提交就是这套组合的发布点
git -C .. commit -am "release: data v0.2.0"
# 3) 造镜像（可加 --tag 打版本标签）
deploy/build-release.sh --tag=2026.06.07
```

`build-release.sh` 用你**本机的 git 凭据/SSH** 克隆私有仓，凭据不进镜像。前置：先建好基础镜像
`(cd .. && scripts/build-base-image.sh)`。

## 运行：一进程一容器（唯一形态）

每个服务一个容器，同一镜像、不同 `command`（崩溃隔离、独立重启、与 k8s 对齐）。
「跑一个就有全部」由一条 compose 提供：

```bash
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps      # 各服务 healthy
```

单独跑某个服务：

```bash
docker run --rm -p 8765:8765 -v vortex-workspace:/workspace vortex:latest vortexctl data
# 裸 `docker run vortex:latest`（不带服务名）会打印用法并列出已装入服务
```

规范端口：data `8765` · qmt `8810` · backtest `8767` · trader `8820`(预留)。
默认只绑宿主机回环（仅本机可访问）；对外暴露需先配各服务写接口 token，再把对应 `*_BIND_ADDR` 设为 `0.0.0.0`。

## 本地调试（不走发版流程）

改完代码临时自测——**不切路径、不提交、不打 tag**。两种粒度：

**① 单服务（最常用）** —— 在你正改的那个仓里，用它自己的 Dockerfile/compose 打本地镜像：

```bash
(cd ../vortex_common && scripts/build-base-image.sh)   # 一次性：建好 vortex-base，之后本地离线可跑
# 在服务仓内（如 vortex_data）——compose 用本仓 Dockerfile 构建本地代码（含未提交改动）并运行：
docker compose up -d --build
```

**② 全栈** —— 用本地代码打整组合镜像（`build-release.sh` 的本地源覆盖，不走 git）：

```bash
VORTEX_DATA_SRC=../vortex_data deploy/build-release.sh --tag=dev               # 仅 data 用本地
VORTEX_DATA_SRC=../vortex_data VORTEX_QMT_SRC=../vortex_qmt \
VORTEX_BACKTEST_SRC=../vortex_backtest deploy/build-release.sh --tag=dev       # 全栈本地
VORTEX_IMAGE=vortex:dev docker compose -f deploy/docker-compose.yml up -d
```

未设 `*_SRC` 的服务仍按 `versions.yml` 的 tag 从 git 拉，发版流程不受影响。

## 启动契约（common 调各服务的通用位置脚本）

`vortexctl <svc>` 启动单个服务时：

1. 优先执行该仓的 **`/app/services/vortex_<svc>/deploy/run.sh`**（各仓自描述如何启动自己）；
2. 不存在则回退到 `vortexctl` 的**内置默认命令**（当下三仓未加 run.sh 也能直接跑）。

各仓后续补 `deploy/run.sh` 的约定见各自迁移指引（[migration/](../docs/migration/README.md)）。
`vortexctl list` 可查看每个服务当前走的是 run.sh 还是内置默认。

## qmt 配置（实盘）

qmt 需要风控/桥接参数，compose 默认从 `deploy/qmt.env` 读（`VORTEX_QMT_ENV` 可改路径）。
至少配置：`QMT_BRIDGE_BASE_URL`（指向 Windows 上的 qmt-bridge）、`QMT_BRIDGE_TOKEN`、
`VORTEX_QMT_TOKEN`（写接口）、实盘门禁 `VORTEX_QMT_ENABLE_TRADING` 等。

## 升级到 Kubernetes

主形态已是「一镜像多容器」，平移直接：每个 compose 服务 → 一个 Deployment（同镜像、
`command: ["vortexctl","<svc>"]`），Service 暴露端口，PVC 替代命名卷，healthcheck → liveness/readiness probe。
