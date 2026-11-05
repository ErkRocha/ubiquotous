"""Least time: manda para quem está respondendo MAIS RÁPIDO.

Cada upstream tem uma média móvel (EWMA) do tempo de resposta. A nota de cada
um é `latência média × (conexões ativas + 1)`: um servidor rápido mas já
ocupado pode perder para um um pouco mais lento e livre. A ideia é a mesma do
`least_time` do NGINX Plus.

Upstream ainda sem medição tem nota 0, então todo mundo é experimentado logo
no começo. Empates são resolvidos aleatoriamente.

Para ver o efeito: suba com API_RUST_LATENCY_MS=200 e observe o api-rust
recebendo cada vez menos requisições.
"""

import random

from .base import Balancer


class LeastTime(Balancer):
    name = "least_time"

    def __init__(self, pool_name: str, rng: random.Random | None = None):
        super().__init__(pool_name)
        self.rng = rng or random.Random()

    @staticmethod
    def score(upstream) -> float:
        if upstream.latency_ewma_ms is None:
            return 0.0
        return upstream.latency_ewma_ms * (upstream.active_connections + 1)

    def pick(self, candidates, ctx):
        best = min(self.score(u) for u in candidates)
        return self.rng.choice([u for u in candidates if self.score(u) == best])
