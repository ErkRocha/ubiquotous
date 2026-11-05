"""Least connections: manda para quem tem MENOS requisições em andamento agora.

Funciona bem quando as requisições têm durações muito diferentes: um servidor
preso em requisições lentas acumula conexões abertas e para de receber novas.

Detalhe: com pouco tráfego quase todos têm 0 conexões. Se o empate fosse
resolvido sempre pelo primeiro da lista, ele receberia tudo; por isso o
desempate é aleatório.
"""

import random

from .base import Balancer


class LeastConnections(Balancer):
    name = "least_connections"

    def __init__(self, pool_name: str, rng: random.Random | None = None):
        super().__init__(pool_name)
        self.rng = rng or random.Random()

    def pick(self, candidates, ctx):
        fewest = min(u.active_connections for u in candidates)
        return self.rng.choice([u for u in candidates if u.active_connections == fewest])
