"""Algoritmos de load balancing. Cada um está em um arquivo, com a explicação."""

from .base import Balancer, PickContext
from .ip_hash import IpHash
from .least_connections import LeastConnections
from .least_time import LeastTime
from .random_two_choices import RandomTwoChoices
from .round_robin import RoundRobin
from .sticky_round_robin import StickyRoundRobin

STRATEGIES: dict[str, type[Balancer]] = {
    cls.name: cls
    for cls in (RoundRobin, StickyRoundRobin, LeastConnections, LeastTime, IpHash, RandomTwoChoices)
}


def make_balancer(strategy: str, pool_name: str) -> Balancer:
    try:
        return STRATEGIES[strategy](pool_name)
    except KeyError:
        raise ValueError(f"estratégia desconhecida {strategy!r}; use uma de: {', '.join(STRATEGIES)}") from None


__all__ = ["Balancer", "PickContext", "STRATEGIES", "make_balancer"]
