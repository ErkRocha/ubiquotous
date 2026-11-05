"""Sticky round-robin (sessão "grudenta").

A primeira requisição de um cliente é distribuída por round-robin. O gateway
devolve um cookie dizendo qual upstream atendeu; nas próximas requisições, o
cliente manda o cookie de volta e cai no MESMO upstream.

Útil quando o servidor guarda estado em memória (sessão, carrinho, cache
local). Se o upstream "grudado" ficar indisponível, o cliente é redistribuído
e recebe um cookie novo.

Teste: curl -c /tmp/c -b /tmp/c -i localhost:8080/users  (várias vezes)
"""

from .base import Balancer
from .round_robin import RoundRobin


class StickyRoundRobin(Balancer):
    name = "sticky_round_robin"

    def __init__(self, pool_name: str):
        super().__init__(pool_name)
        self.cookie_name = f"gw_sticky_{pool_name}"
        self.round_robin = RoundRobin(pool_name)

    def pick(self, candidates, ctx):
        wanted = ctx.cookies.get(self.cookie_name)
        for upstream in candidates:
            if upstream.name == wanted:
                return upstream
        return self.round_robin.pick(candidates, ctx)

    def response_cookies(self, upstream, ctx):
        if ctx.cookies.get(self.cookie_name) == upstream.name:
            return {}
        return {self.cookie_name: upstream.name}
