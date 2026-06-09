# ADR-001: Vortex 统一发布与部署架构

**状态：** Proposed（待你拍板转 Accepted）
**日期：** 2026-06-07
**决策人：** @zyukyunman（owner）
**相关：** [docs/migration/](../migration/README.md)（各仓库切到 vortex-base 的迁移）

## 背景（Context）

Vortex 由多个独立 git 仓库组成：基础设施 `vortex_common`，以及服务仓
`vortex_data`（行情采集/查询，HTTP）、`vortex_qmt`（实盘交易，HTTP + 经 qmt-bridge 接 Windows）、
`vortex_backtest`（回测，HTTP）、`vortex_trader`（预留，当前空仓）。前一步已把三仓的共用第三方
依赖统一进 `vortex-base` 基础镜像。

现在要解决**发布与部署**：
- 希望打造**一个镜像**，里面就是各仓库 main 分支（或指定 tag）的代码；用户拿到镜像启动后即可使用全部功能。
- 发版通过「改配置里的 tag → 调脚本拉代码造镜像 → 提交版本」完成。
- 服务启动由 common 的脚本统一执行；各服务在**通用位置**提供启动脚本，common 默认去调用。

**约束与现状（影响方案的关键事实）：**
- 服务异构：`vortex-data` 启动是 `vortex-data --root <ws> init && server start`；qmt/backtest 是 `vortex-<svc> serve`——**启动方式不统一**，不宜由 common 硬编码。
- 端口冲突：data 与 backtest 默认都用 `8765`；qmt 用 `8810`。
- 资源/生命周期差异大：data 稳态 I/O 常驻；backtest 突发计算（重 CPU）；qmt 是**实盘交易**、带风控门禁、需接 Windows 主机，最需要隔离与独立重启。
- 数据流：data 写 workspace → backtest 只读消费 workspace；qmt、backtest 各有 state。
- 部署规模：单机为主（owner 自用/小团队），qlib 已出局 → 镜像跨架构（amd64/arm64 通用）。
- 仓库是私有的：build 时拉代码涉及 git 凭据。

**你已定的输入：** 版本模型＝**每仓库各自 tag**；首版纳入 **data/qmt/backtest + 预留 trader**；
拓扑与部署目标＝**由我推荐**；非 root＝**由我定**。

## 决策（Decision）

**一个版本化镜像 `vortex:<tag>`，内含全部服务代码（各仓按 `deploy/versions.yml` 钉定的 tag 装入）；
唯一运行形态＝「同一镜像 + 多容器（每服务一个容器，一进程一容器，与 k8s 对齐）」。**
common 提供统一启动器 `vortexctl <svc>`（前台跑单个服务），各服务在通用位置 `deploy/run.sh`
暴露自己的启动方式，`vortexctl` 默认调用它（缺失时回退到内置默认命令，保证当下即可跑）。

> 不做「单容器跑全部」的便捷模式——维护两套形态不划算，且与 k8s 的一进程一容器相悖。
> 「跑一个就有全部」的便利改由**部署侧一条 `docker compose up`** 提供（仍是一个镜像、一次拉取）。
> 本地改代码自测的便利由**调试流程**（各仓本地构建，见下）提供，与发版流程解耦。

四条子决策：

1. **镜像（一个，含全部代码）**：多阶段 Dockerfile `FROM vortex-base`，把各服务源码（预先 clone 到
   pinned tag）`pip install --no-deps` 进去 + 装 common 启动器。镜像内含所有服务的 console 入口
   （`vortex-data/-qmt/-backtest`）与 `vortexctl`。各仓的版本 ref 以 OCI label 烙进镜像，可追溯。

2. **运行（唯一形态：一进程一容器）**：顶层 `deploy/docker-compose.yml` 为每个服务起一个容器，
   `image` 都是 `vortex:<tag>`，各自 `command: ["vortexctl","<svc>"]`、各自端口/卷/healthcheck。
   Docker（或 k8s）即进程监督者，单服务崩溃/重启互不影响（**qmt 实盘与 backtest 重算彻底隔离**）。
   裸 `docker run vortex:<tag>` 不带服务名时打印用法并列出已装入服务，引导你选服务或用 compose。

3. **发布（每仓库各自 tag）**：`deploy/versions.yml` 钉每个仓库的 git ref；`deploy/pull-code.sh`
   按 ref 把各仓拉到 `deploy/repos/<svc>`，并首次从各仓 `.env.example` 种出 `.env`（配置归各仓所有，
   `.env` 被各仓 gitignore、含密钥不入库），`deploy/build-release.sh` 再用 `repos/` 的代码构建镜像并烙
   ref label（**各仓 `.env` 不进镜像**）。
   **发版＝改 versions.yml 里某仓的 tag + 提交**（该提交即这套组合的发布点）。

4. **非 root + 单机优先**：镜像内建非 root 用户 `vortex`(uid 1000)，数据目录预置属主；配合**命名卷**
   （Docker 按镜像属主初始化，规避 bind-mount 的 uid 错配）默认非 root 运行。单机 Docker/Compose 为
   一等部署；k8s 作为有清晰升级路径的二等目标（每个 compose 服务 → 一个 Deployment，同镜像不同 command）。

## 考虑过的方案（Options Considered）

### 方案 A：单容器全家桶（仅此一种）
一个容器内由监督器（supervisord / bash）跑全部服务。

| 维度 | 评估 |
|------|------|
| 复杂度 | 低（一个容器） |
| 隔离/可靠性 | **差**——一服务崩溃/OOM 易波及他者；实盘 qmt 与重算 backtest 抢资源 |
| 运维（日志/重启/扩缩） | 差——日志混流、无法单服务重启、无法单独限流 |
| 上 k8s | 差——与「一进程一容器」相悖，等于重做 |
| 贴合诉求 | 高——「跑一个就有全部」 |

### 方案 B：一个镜像 + 多容器（compose 每服务一容器）✅ 主
同一 `vortex:<tag>`，compose 起多容器，各自 `command`/端口/卷/探针。

| 维度 | 评估 |
|------|------|
| 复杂度 | 中（一份顶层 compose） |
| 隔离/可靠性 | **好**——崩溃隔离、单服务重启、各自资源限额；qmt 实盘独立 |
| 运维 | 好——日志分流、healthcheck 独立、可单独滚动更新 |
| 上 k8s | **好**——每服务直接映射成 Deployment（同镜像换 command） |
| 贴合诉求 | 高——仍是「一个镜像、一个 tag、一次拉取」 |

### 方案 C：每服务各自独立镜像 + 顶层 compose
回到多镜像，各自 Dockerfile/tag。

| 维度 | 评估 |
|------|------|
| 复杂度 | 高——N 个镜像各自构建/版本/推送 |
| 单一交付物 | **差**——用户要拉 N 个镜像，违背「一个镜像装全部」 |
| 复用 base 缓存 | 一般 |
| 贴合诉求 | 低 |

## 取舍分析（Trade-off Analysis）

诉求里「一个镜像、启动即用全部」与工程上的「隔离/可运维/可演进」看似冲突，**B 同时满足两者**：
交付物仍是单一镜像（满足「一个镜像装全部代码、一次拉取」），但运行时按服务拆容器（拿回崩溃隔离、
独立重启、独立资源与日志）。代价仅是多一份顶层 compose——可接受。

「跑一个就有全部」的便利由**一条 `docker compose up`** 提供，无需再造「单容器全家桶」模式——
后者要额外维护一套进程监督逻辑、与 k8s 的一进程一容器相悖，得不偿失。**只保留 B 一种形态，维护面最小。**

纯 A（单容器全家桶为唯一/便捷形态）被否：多维护一套监督逻辑，且实盘交易与重算回测同容器，崩溃与
资源争用风险对**交易系统**不可接受。纯 C 被否：违背「一个镜像装全部」，且把版本/构建复杂度乘以服务数。

**启动契约**用「各服务 `deploy/run.sh` + common 默认调用」而非 common 硬编码，正是因为三服务启动方式不统一；
让每个服务自描述启动、common 只负责编排，是把"知道怎么起自己"的知识留在各自仓库——解耦、可独立演进。

## 后果（Consequences）

**更容易：**
- 发版＝改 `versions.yml` 一个 tag + 提交；一条 `build-release.sh` 出一个可追溯（ref 烙 label）的镜像。
- 用户：一条 `docker compose up` 起全部服务即可用全部功能（单服务可 `docker run … vortexctl <svc>`）。
- 演进到 k8s：每服务已是独立容器/进程，平移成 Deployment 即可。
- qmt 实盘获得独立重启/资源/日志，安全性与可运维性提升。

**更难 / 需注意：**
- 端口冲突必须解决：**规范内部端口** data `8765`、qmt `8810`、backtest `8767`（部署期 env 覆盖其默认 8765）、trader `8820`(预留)。
- 各仓需新增 `deploy/run.sh`（启动契约）——`vortexctl` 暂以内置默认兜底，但长期应由各仓补齐（计入迁移指引）。
- 拉私有仓需 git 凭据：由 `pull-code.sh` 在**宿主机**用你现有 SSH/凭据克隆到 `deploy/repos/`，再由 build 选取代码，**凭据与各仓 `.env` 都不进镜像**。
- 镜像变大（含全部服务代码，但依赖已在 base 共享层）——对单机部署可接受。
- 非 root + bind-mount 在 Linux 可能 uid 错配：默认用**命名卷**规避；需 bind-mount 开发时用文档化的 `PUID`/`user:` 覆盖或 root 回退。

**需要复审的点：**
- 若将来服务很多/团队变大，可重新评估 C（独立镜像）以换更细的构建与发布粒度。

## 发布流程 vs 调试流程（两条独立路径）

**发布（可复现）**：改 `versions.yml` 某仓 tag → 提交 → `deploy/pull-code.sh` 按 tag 拉各仓到
`repos/` → 填各仓 `.env` → `deploy/build-release.sh` 用 `repos/` 造组合镜像 `vortex:<tag>`。
版本由 git tag 钉死、各仓 ref 烙进镜像 label；各仓 `.env`（配置）不进镜像，运行时由 compose 注入。

**调试（本地、不走 git、不切路径）**：在你正改的那个仓里，一条 `docker compose up -d --build`——
compose 用该仓自己的 `Dockerfile` 构建本地工作区代码（含未提交改动）并跑起来自测，不提交、不打 tag。
一次性建好 `vortex-base` 后整条 loop 本地离线可跑。这条是各仓 base 迁移的"自然副产品"（每仓迁移后
都有自己的 Dockerfile/compose），**无需任何额外脚本**——各仓那套各异的 `scripts/build-image.sh` 可一并删除。

需要用本地代码验**整组合镜像**（全栈联调）时，`build-release.sh` 支持本地源覆盖：
`VORTEX_DATA_SRC=../vortex_data deploy/build-release.sh --tag=dev` 用本地代码替换该服务、其余仍按 tag。

## 端口 / 卷 / 启动契约（落地规范）

**规范端口（容器内）：** data `8765`、qmt `8810`、backtest `8767`、trader `8820`(预留)。
**命名卷：** `vortex-workspace`（data 读写 → backtest 只读）、`vortex-qmt-state`、`vortex-backtest-state`。
**启动契约：** 各仓提供 `deploy/run.sh`（读统一 env：`VORTEX_<SVC>_HOST/PORT`、`VORTEX_WORKSPACE`、`VORTEX_STATE`，前台 exec 自身服务）。
`vortexctl <svc>` 优先调用该脚本；不存在时回退内置默认命令。一进程一容器，无「单容器跑全部」模式。

## 行动项（Action Items）

1. [ ] 落地 `deploy/`：`versions.yml`、组合 `Dockerfile`、`bin/vortexctl`、顶层 `docker-compose.yml`、`build-release.sh`、`README.md`（本 ADR 同批提交骨架）。
2. [ ] 各仓新增 `deploy/run.sh` 启动契约（计入三仓迁移指引，下游 session 执行）。
3. [ ] 各仓首次发布打 tag，并写进 `deploy/versions.yml`。
4. [ ] 跑 `build-release.sh` 产出 `vortex:latest`，`docker compose up` 验证多容器编排。
5. [ ] owner 复审本 ADR → 转 Accepted。
