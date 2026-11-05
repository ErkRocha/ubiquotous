"""Interface comum dos algoritmos de load balancing."""

from dataclasses import dataclass, field

from ..upstream import Upstream


@dataclass
class PickContext:
    """O que o algoritmo sabe sobre a requisição."""

    client_ip: str = ""
    cookies: dict[str, str] = field(default_factory=dict)
    # Todos os upstreams do pool, inclusive os indisponíveis. Só o ip_hash usa:
    # ele precisa de uma lista estável para o mesmo IP cair sempre no mesmo lugar.
    pool: list[Upstream] = field(default_factory=list)


class Balancer:
    name = "base"

    def __init__(self, pool_name: str):
        self.pool_name = pool_name

    def pick(self, candidates: list[Upstream], ctx: PickContext) -> Upstream:
        """Escolhe um entre os `candidates` (sempre não vazio e só com upstreams
        disponíveis: saudáveis e com o circuit breaker permitindo)."""
        raise NotImplementedError

    def response_cookies(self, upstream: Upstream, ctx: PickContext) -> dict[str, str]:
        """Cookies que o gateway deve devolver ao cliente (só o sticky usa)."""
        return {}
