"""Round-robin: um de cada vez, em fila. A, B, C, A, B, C...

Simples e justo quando todos os servidores são iguais e as requisições custam
mais ou menos o mesmo. Não olha carga nem latência: um servidor lento recebe
a mesma quantidade de requisições que um rápido.
"""

from .base import Balancer


class RoundRobin(Balancer):
    name = "round_robin"

    def __init__(self, pool_name: str):
        super().__init__(pool_name)
        self.counter = 0

    def pick(self, candidates, ctx):
        upstream = candidates[self.counter % len(candidates)]
        self.counter += 1
        return upstream
