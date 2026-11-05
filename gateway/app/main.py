"""Ponto de entrada: monta o app aiohttp.

    python -m app.main     (ou: docker compose up -d gateway)
"""

import asyncio
import contextlib
import logging

import aiohttp
from aiohttp import web

from . import admin, config
from .config import Config
from .envelope import error
from .gateway import Gateway
from .health import HealthChecker

GATEWAY = web.AppKey("gateway", Gateway)


def create_app(cfg: Config) -> web.Application:
    gw = Gateway(cfg)
    app = web.Application()
    app[GATEWAY] = gw

    # Rotas do próprio gateway primeiro; todo o resto vai para o pipeline.
    async def unknown_admin_route(_):
        return error(404, "NOT_FOUND", "Rota não encontrada.")

    app.add_routes(admin.routes(gw))
    app.router.add_route("*", "/_gateway/{tail:.*}", unknown_admin_route)
    app.router.add_route("*", "/{tail:.*}", gw.handle)

    async def lifecycle(app: web.Application):
        # Uma sessão HTTP para todos os upstreams: reaproveita conexões (keep-alive).
        # auto_decompress=False: o corpo é repassado exatamente como veio.
        gw.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=1000), auto_decompress=False)
        health_task = None
        if cfg.health_enabled:
            checker = HealthChecker(
                list(gw.upstreams.values()), gw.session, path=cfg.health_path, interval=cfg.health_interval,
                timeout=cfg.health_timeout, unhealthy_threshold=cfg.health_unhealthy_threshold,
                healthy_threshold=cfg.health_healthy_threshold,
            )
            health_task = asyncio.create_task(checker.run_forever())
        yield
        if health_task:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task
        await gw.session.close()

    app.cleanup_ctx.append(lifecycle)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    cfg = config.load()
    log = logging.getLogger("gateway")
    for pool in cfg.pools:
        log.info("pool %-16s strategy=%-20s upstreams=%s", pool.name, pool.strategy, ", ".join(pool.upstreams))
    web.run_app(create_app(cfg), port=cfg.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
