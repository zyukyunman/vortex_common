# 拉代码 → 改配置 → 起服务（操作指南）

> 一句话：**配置归各仓所有**，在各仓固定路径 `<仓>/.env`（真名、已提交、含默认值+你填的密钥）。
> common 只负责编排：把各仓拉到 `deploy/repos/<svc>`，你就地改它的 `.env`，再造镜像、起容器。
> 配置不在镜像里——改完 `up -d` / `restart` 即生效，不重建镜像。

> **约定：所有 `docker compose` 命令都在 `vortex_common/deploy/` 目录里执行**（这样 compose 能
> 正确读到 `repos/<svc>/.env`）。先 `cd vortex_common/deploy`。

---

## 0. 配置在哪——先建立这张地图

| 配置类型 | 放在哪 | 谁改 | 改了怎么生效 | 例子 |
|---------|--------|------|------------|------|
| **部署层**（token、URL、风控；端口由 registry 钉死、不在 .env 改） | 各仓 `<仓>/.env`（= `deploy/repos/<svc>/.env`） | 你 | `vortex run up <svc>` 重建容器 | TUSHARE_TOKEN、QMT_BRIDGE_BASE_URL |
| **运行层**（抓取计划、lane、保留空间） | workspace 数据卷里的 `profiles/`、`state/control.db` | 控制台/CLI | 不用重启，scheduler 每分钟重读 | scheduler 时间 |

绝大多数人只动**部署层**的各仓 `.env`。下面从它开始。

---

## 1. 拉代码（把各仓代码+配置拉到本地）

```bash
cd vortex_common/deploy
./pull-code.sh                 # 按 versions.yml 把各仓拉到 deploy/repos/<svc>
# 只拉部分： ./pull-code.sh data
```

它做两件事：① 把各仓克隆/更新到 `deploy/repos/vortex_data` 等；② 首次从各仓 `.env.example`
拷一份 `.env` 供你填密钥（`.env` 被各仓 gitignore、含密钥不入库；后续更新不覆盖你填好的 `.env`）。

> 前置：各仓需提供 `.env.example`（仓根，URL 等默认值填好、token 留空）。若某仓还没有，
> pull-code 会提示；按迁移指南补（见 `docs/migration/README.md` §5）。

---

## 2. 改配置（就地改各仓的 .env）

用编辑器打开要改的那个仓的 `.env`，填密钥/凭证。最常见的：

```bash
# 数据服务：deploy/repos/vortex_data/.env
TUSHARE_TOKEN=你的tushare_token            # 必填，否则抓数 blocked_credentials
VORTEX_DATA_DASHBOARD_TOKEN=               # 要用写操作/对外暴露才需要；生成：python3 -c "import secrets;print(secrets.token_hex(24))"
```

```bash
# 实盘服务：deploy/repos/vortex_qmt/.env（只跑数据可忽略）
VORTEX_QMT_TOKEN=                          # 写接口 token（下单/调仓）
QMT_BRIDGE_BASE_URL=http://<Windows-IP>:8000   # 指向 qmt-bridge
QMT_BRIDGE_TOKEN= ; QMT_ACCOUNT_ID=        # 桥接鉴权 + 账户
```

> token 是你**设一次就固定**的值（别频繁换，调用方要跟着改）。URL 这类一次填好即可。

---

## 3. 造镜像 + 起服务

```bash
cd vortex_common/deploy
./build-release.sh                          # 用 repos/ 的代码造 vortex:latest（各仓 .env 不进镜像）
vortex run up data                          # 先只起数据服务，最稳
# 全栈（data+qmt+backtest）： vortex run deploy
docker compose ps                           # 等到 healthy
docker compose logs -f vortex-data
```

> 首次起 data 会自动在数据卷里 init，无需手动初始化。

---

## 4. 改完配置后怎么「再拉起」

改了 `deploy/repos/<svc>/.env` 任何值后，重跑同一条 `vortex run up` 即可，compose 检测到变化会重建容器：

```bash
cd vortex_common/deploy
vortex run up data
```

不需要 down、不需要重新 `build-release.sh`（代码没变就不重建镜像）。数据在卷里，重建容器**不丢**。

---

## 5. 对外暴露（云服务器公网/内网访问）

端口由 registry 钉死（内==外、不再重映射）；绑定地址不在各仓 `.env`，而是 `vortex run` 时用 shell env 覆盖（默认只绑回环、最安全）。
**先确保设了对应服务的写 token**，再：

```bash
VORTEX_DATA_BIND_ADDR=0.0.0.0 vortex run deploy
```

> 端口由 registry 钉死（内==外、不再重映射），对外只需把绑定地址放开到 `0.0.0.0`。

然后放行云服务器安全组/防火墙对应端口。（顺序：先有写 token，再开 0.0.0.0，避免裸暴露写接口。）

---

## 6.（可选）数据落到指定磁盘

默认数据写进 Docker 命名卷 `vortex-workspace`（够用、不丢）。要落到云服务器数据盘，改
`deploy/docker-compose.yml` 里 `vortex-data` 的 `volumes` 为宿主机目录，并 `chown -R 1000:1000`
（容器以 uid 1000 运行）。改完按 §4 重新 `vortex run up data`。

---

## 速查：常见坑

| 现象 | 原因 | 解决 |
|------|------|------|
| `vortex run` 报 env file `repos/.../.env` not found | 没先 `./pull-code.sh`，或该仓没 `.env.example` | 先 pull-code；缺模板的仓按迁移指南 §5 补 |
| 改了 `.env` 没效果 | 没在 `deploy/` 里跑，或没重新 `vortex run` | `cd deploy` 后重跑 `vortex run up <svc>` |
| 抓数一直 blocked_credentials | `TUSHARE_TOKEN` 没填 | 填进 `repos/vortex_data/.env` 后 `vortex run up data` |
| 写操作 401 | 没设对应服务的写 token | 设 token 后 `vortex run up <svc>`，请求带 token |
| 重新 pull-code 后我填的 .env 没了 | 该仓 `.env` 没被 gitignore（被 checkout 覆盖了） | 确认该仓 `.gitignore` 含 `.env`（迁移指南 §5）|

## 常用命令（均在 vortex_common/deploy/ 下）

```bash
./pull-code.sh                       # 拉/更新各仓代码到 repos/
./build-release.sh                   # 造组合镜像
vortex run up data                   # 起/重建数据服务
vortex run deploy                    # 起全栈
docker compose ps                    # 健康状态
docker compose logs -f vortex-data   # 日志
docker compose down                  # 停并删容器（数据卷保留）
```
