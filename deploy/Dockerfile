# ============================================================================
# Vortex 组合镜像：一个镜像装下全部服务代码（各仓按 versions.yml 钉定的 tag）。
#
# 由 deploy/build-release.sh 构建：pull-code.sh 先把各仓拉到 deploy/repos/<svc>，build-release
# 再把代码暂存到 deploy/.stage/<svc>（排除各仓 .env，配置不入镜像），以 deploy/ 为上下文构建本文件。
#
# 运行：见 deploy/docker-compose.yml（每服务一容器）。单服务：docker run vortex:<tag> vortexctl <svc>。
# ============================================================================
ARG BASE_IMAGE=vortex-base:latest
FROM ${BASE_IMAGE}

# 各仓版本 ref（由 build-release.sh 注入），仅用于烙进镜像 label 便于追溯。
ARG VORTEX_DATA_REF=unknown
ARG VORTEX_QMT_REF=unknown
ARG VORTEX_BACKTEST_REF=unknown
ARG VORTEX_TRADER_REF=none

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    VORTEX_WORKSPACE=/workspace \
    VORTEX_STATE=/state

WORKDIR /app

# 1) 各服务源码（build-release.sh 已 clone 到 pinned tag）。trader 预留时为占位空目录。
COPY .stage/vortex_data     /app/services/vortex_data
COPY .stage/vortex_qmt      /app/services/vortex_qmt
COPY .stage/vortex_backtest /app/services/vortex_backtest
COPY .stage/vortex_trader   /app/services/vortex_trader

# 2) 安装各服务（依赖已在 vortex-base，--no-deps 不再解析）。
#    qmt 的 qmt-bridge 子模块零依赖单独装；trader 仅在检出了代码时才装。
RUN set -eux; \
    pip install --no-deps --no-build-isolation /app/services/vortex_data; \
    pip install --no-deps --no-build-isolation /app/services/vortex_qmt; \
    if [ -f /app/services/vortex_qmt/external/qmt-bridge/pyproject.toml ]; then \
        pip install --no-deps /app/services/vortex_qmt/external/qmt-bridge; \
    fi; \
    pip install --no-deps --no-build-isolation /app/services/vortex_backtest; \
    if [ -f /app/services/vortex_trader/pyproject.toml ]; then \
        pip install --no-deps --no-build-isolation /app/services/vortex_trader; \
    fi

# 3) common 统一启动器
COPY bin/vortexctl /usr/local/bin/vortexctl
RUN chmod +x /usr/local/bin/vortexctl

# 4) 非 root：建 vortex 用户，预置数据目录（每服务独立容器，各自挂 /workspace 或 /state）
RUN useradd -r -u 1000 -m -d /home/vortex vortex \
    && mkdir -p "${VORTEX_WORKSPACE}" "${VORTEX_STATE}" \
    && chown -R vortex:vortex /app "${VORTEX_WORKSPACE}" "${VORTEX_STATE}"
USER vortex

LABEL org.opencontainers.image.title="vortex" \
      org.opencontainers.image.description="All-in-one Vortex services image (data/qmt/backtest/trader)" \
      org.opencontainers.image.source="https://github.com/zyukyunman/vortex_common" \
      vortex.ref.data="${VORTEX_DATA_REF}" \
      vortex.ref.qmt="${VORTEX_QMT_REF}" \
      vortex.ref.backtest="${VORTEX_BACKTEST_REF}" \
      vortex.ref.trader="${VORTEX_TRADER_REF}"

# 规范内部端口：data 8765 / qmt 8810 / backtest 8767 /（trader 8820 预留）
EXPOSE 8765 8810 8767

# 唯一运行形态：一进程一容器。运行时必须指定服务（compose/k8s 的 command: ["vortexctl","<svc>"]）。
# 不带参数（裸 docker run）时打印用法与已装入服务，引导你选服务或用 compose。
CMD ["vortexctl"]
