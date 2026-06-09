# deploy/ —— Vortex 组合镜像：发布与部署

一个镜像装下全部服务代码（各仓按 [`versions.yml`](versions.yml) 钉定的 ref）。
**配置归各仓所有**（在各仓 `<仓>/.env`），common 只负责编排。架构见
[ADR-001](../docs/adr/ADR-001-deployment-architecture.md)；逐步操作见
[CONFIG-AND-RUN.zh.md](CONFIG-AND-RUN.zh.md)。

## 是什么

| 文件 | 作用 |
|------|------|
| `versions.yml` | 各仓版本清单（每仓库各自 ref）。改 ref 即发版。 |
| `pull-code.sh` | 按清单把各仓拉到 `deploy/repos/<svc>`，并首次从各仓 `.env.example` 拷出 `.env` 供你填（`.env` 被各仓 gitignore，含密钥不入库） |
| `build-release.sh` | 用 `repos/<svc>` 的代码造 `vortex:<tag>`（FROM `vortex-base`）；**各仓 `.env` 不进镜像**，ref 烙进 label |
| `Dockerfile` | 组合镜像：装入各服务代码（`--no-deps`）+ `vortexctl`，非 root |
| `bin/vortexctl` | 统一启动器：`vortexctl <svc>`（前台单服务）/ `list` |
| `docker-compose.yml` | 顶层编排：每服务一容器，`env_file: repos/<svc>/.env` 运行时注入配置 |
| `CONFIG-AND-RUN.zh.md` | 拉代码 → 改配置 → 起服务的操作指南 |

> `repos/`、`.stage/` 是拉取/构建产物，已被 `.gitignore` 忽略，不入 common 的库。

## 部署流程（在 `deploy/` 内）

```bash
./pull-code.sh                       # 1) 拉各仓到 repos/<svc>（首次从各仓 .env.example 种出 .env）
# 2) 编辑 repos/<svc>/.env 填 token/凭证（URL 等已预填）
./build-release.sh                   # 3) 造组合镜像 vortex:latest（各仓 .env 不进镜像）
docker compose up -d vortex-data     # 4) 起数据服务；或 docker compose up -d 全栈
docker compose ps                    # healthy
```

**发版**＝改 `versions.yml` 某仓 ref → 提交 → `./pull-code.sh && ./build-release.sh`。
`pull-code.sh` 用你**本机 git 凭据/SSH** 克隆私有仓；凭据与各仓 `.env` 都不进镜像。
前置：先建好基础镜像 `(cd .. && scripts/build-base-image.sh)`。

## 运行：一进程一容器

每服务一容器，同一镜像、不同 `command`（崩溃隔离、独立重启、对齐 k8s）。规范端口
data `8765` · qmt `8810` · backtest `8767` · trader `8820`(预留)。默认只绑回环；对外暴露在
`up` 时用 shell env 覆盖（**先配写 token**）：

```bash
VORTEX_DATA_BIND_ADDR=0.0.0.0 VORTEX_DATA_PUBLIC_PORT=8876 docker compose up -d vortex-data
```

## 本地调试（不走发版流程）

- **单服务（最常用）**：在你正改的那个仓里 `docker compose up -d --build`——compose 用本仓
  `Dockerfile` 构建本地工作区代码（含未提交改动）并运行，无需任何脚本。
- **全栈用本地代码**：本地源覆盖 `repos/<svc>`：
  `VORTEX_DATA_SRC=../vortex_data ./build-release.sh --tag=dev`（其余服务用 `repos/<svc>`）。

## 启动契约

`vortexctl <svc>` 优先执行该仓 `/app/services/vortex_<svc>/deploy/run.sh`（各仓自描述如何启动自己），
不存在则回退内置默认命令。`vortexctl list` 查看每个服务走的是 run.sh 还是内置默认。

## 升级到 Kubernetes

每个 compose 服务 → 一个 Deployment（同镜像、`command: ["vortexctl","<svc>"]`），Service 暴露端口，
PVC 替代命名卷，各仓 `.env` → ConfigMap/Secret，healthcheck → liveness/readiness probe。
