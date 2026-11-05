"""Health check ATIVO: o gateway pergunta periodicamente "você está vivo?".

A cada `interval_seconds` faz GET /health em cada upstream. Depois de
`unhealthy_threshold` falhas seguidas o upstream sai da rotação; depois de
`healthy_threshold` sucessos seguidos ele volta.

Ativo x passivo:
- o health check descobre que um servidor caiu mesmo SEM tráfego, mas só a cada
  intervalo;
- o circuit breaker (passivo) reage na hora às falhas reais, mas só se houver
  tráfego. Os dois se complementam.
"""

import asyncio
import logging

import aiohttp

from .upstream import Upstream

log = logging.getLogger("gateway.health")


class HealthChecker:
    def __init__(self, upstreams: list[Upstream], session: aiohttp.ClientSession, *, path: str,
                 interval: float, timeout: float, unhealthy_threshold: int, healthy_threshold: int):
        self.upstreams = upstreams
        self.session = session
        self.path = path
        self.interval = interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self.streaks = {u.name: 0 for u in upstreams}  # >0 sucessos seguidos, <0 falhas seguidas

    async def run_forever(self) -> None:
        while True:
            await self.check_all()
            await asyncio.sleep(self.interval)

    async def check_all(self) -> None:
        await asyncio.gather(*(self.check(u) for u in self.upstreams))

    async def check(self, upstream: Upstream) -> None:
        try:
            async with self.session.get(upstream.url + self.path,
                                        timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                ok = resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            ok = False

        streak = self.streaks[upstream.name]
        if ok:
            streak = streak + 1 if streak > 0 else 1
            if not upstream.healthy and streak >= self.healthy_threshold:
                upstream.healthy = True
                log.warning("health %s: voltou (UP)", upstream.name)
        else:
            streak = streak - 1 if streak < 0 else -1
            if upstream.healthy and -streak >= self.unhealthy_threshold:
                upstream.healthy = False
                log.warning("health %s: fora do ar (DOWN) após %d falhas", upstream.name, -streak)
        self.streaks[upstream.name] = streak
