# ADR-003: 统一配置架构

**状态：** Accepted
**日期：** 2026-06-10
**决策人：** @zyukyunman（owner）
**相关：** ADR-001（部署架构）、ADR-002（workspace/state 变量）、spec `docs/superpowers/specs/2026-06-09-vortex-config-architecture-design.md`

---

## 背景

Vortex 五仓（common/data/qmt/backtest/trader）的配置（端口、路径、TZ、网络）此前散落在各仓 `.env`/`.env.example`/compose/Dockerfile/launcher/文档中，没有单一真值源，已发生漂移（如 data 端口漂成 8888、各处端口表不一致、写死的 mac 路径）。ADR-002 已统一**代码层**的 `VORTEX_WORKSPACE`/`VORTEX_STATE` 读取；本 ADR 解决**配置层**的单一真值源与防漂移。

## 决策

1. **`config/registry.yml` 为配置单一真值源**；`vortex cfg gen` 投影出 `vortex.generated.env`、`deploy/versions.yml`（保持 awk 可解析的窄字段 name/repo/ref/submodules）、`docs/reference/services.md`（服务总表）、`docs/reference/architecture.md`（mermaid 拓扑）。人只改 registry.yml，其余皆派生。
2. **端口"一号到底、内外一致"**：data 8765 / backtest 8766 / qmt 8767 / trader 8768；compose 端口映射写成 `${...BIND_ADDR}:${...PORT}:${...PORT}`（两端同号，由构造保证内外一致）；删除 `*_PUBLIC_PORT` 重映射旋钮，保留 `*_BIND_ADDR`（默认 127.0.0.1 只绑回环，对外暴露才设 0.0.0.0）。
3. **`vortex` CLI 三组 cfg/image/run**（宿主机编排层），与容器内进程启动器 `vortexctl` 分层（不混）。本阶段交付 cfg 组；image/run 为后续 Phase（收编现有 build-base/pull-code/build-release 脚本与 compose 调用）。
4. **compose 配置注入**：`vortex run` 用 `docker compose --env-file <服务.env> --env-file <common 生成 env>`（末位优先 → common 对冲突项权威）；裸 `docker compose up` 因端口只在生成 env 里、用 `:?` 必填语义大声报错并导向 `vortex run`，不静默成空端口。
5. **容器内监听地址 `0.0.0.0` 是不变量**（容器化服务必须监听容器内所有网卡才能收 docker 转发的流量），不等于对外暴露、不进生成 env；对外暴露只由宿主机侧 `*_BIND_ADDR` 决定。**宿主机 workspace/state 根是机器相关的**，不烤进 committed 生成 env，由 `vortex run` 运行时解析为绝对路径（默认 `$HOME/vortex/workspace`）。容器内路径恒 `/workspace` `/state`（ADR-002）。
6. **`vortex cfg check` 防漂移闸门**：端口唯一/升序、生成物最新（重生 diff）、registry 校验（畸形/重复名/端口越界）、`.env` 禁用键扫描（端口/路径/TZ/绑定不得出现在服务 `.env`，密钥豁免）。挂 pre-commit / CI。
7. **文档分层**：system 级在 common（含生成的 reference + 架构图、ADR、运维手册），service 级在各仓（README/CLAUDE.md/design 日志/in-app 文档站）。

## 后果

- 加服务 = 改 registry.yml 一行 + `vortex cfg gen`；端口内外一致、文档与拓扑图随真值源自动最新。
- 本 ADR **补充** ADR-001/002：端口规范表与配置真值源以本 ADR 与 registry.yml 为准。
- 各仓现存配置/文档需按 spec §8 整改（后续 Phase）：清 `.env` 旧名/端口/路径、compose 改 `${P}:${P}`、in-app 文档站与各仓文档对齐新端口。
