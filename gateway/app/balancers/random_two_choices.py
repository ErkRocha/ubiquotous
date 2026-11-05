"""Random two choices ("power of two choices").

Sorteia DOIS upstreams e fica com o que tem menos conexões ativas.

Por que não olhar todos, como o least_connections? Com vários gateways (ou
várias threads) olhando os mesmos números, todos escolhem ao mesmo tempo o
"menos carregado" e o sobrecarregam (efeito manada). Sortear dois já evita
quase todo o desequilíbrio do aleatório puro, sem esse efeito, e o custo é
constante mesmo com centenas de servidores. É o padrão do Envoy e do NGINX
(`random two least_conn`).
"""

import random

from .base import Balancer


class RandomTwoChoices(Balancer):
    name = "random_two_choices"

    def __init__(self, pool_name: str, rng: random.Random | None = None):
        super().__init__(pool_name)
        self.rng = rng or random.Random()

    def pick(self, candidates, ctx):
        if len(candidates) == 1:
            return candidates[0]
        a, b = self.rng.sample(candidates, 2)
        return b if b.active_connections < a.active_connections else a
