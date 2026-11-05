"""Traffic routing: decide PARA QUAL POOL vai cada requisição.

O load balancer escolhe um servidor DENTRO de um pool; o roteamento vem antes
e escolhe o pool, olhando path, método e headers. Exemplos no gateway.yaml:

- por header:  X-Backend: api-rust    -> pool api-rust
- por path:    /rust/users            -> pool api-rust, que recebe /users
- ponderado:   /canary/users          -> 90% compiled, 10% dynamic (canary)
- padrão:      /users, /health        -> pool all

As rotas são testadas em ordem e vale a primeira que casar.
"""

import random
from dataclasses import dataclass

from .config import RouteConfig


@dataclass
class RouteMatch:
    route: str
    pool: str
    path: str  # path que será repassado ao upstream


class Router:
    def __init__(self, routes: list[RouteConfig], pool_names: set[str], rng: random.Random | None = None):
        self.routes = routes
        self.pool_names = pool_names
        self.rng = rng or random.Random()

    def match(self, method: str, path: str, headers) -> RouteMatch | None:
        for route in self.routes:
            prefix = self._matching_prefix(route, path)
            if prefix is None:
                continue
            if route.methods and method not in route.methods:
                continue
            if any(headers.get(name) != value for name, value in route.headers.items()):
                continue
            if any(name not in headers for name in route.headers_present):
                continue

            pool = self._choose_pool(route, headers)
            if pool is None:
                continue

            upstream_path = path
            if route.strip_prefix and prefix != "/":
                upstream_path = path[len(prefix):] or "/"
            return RouteMatch(route.name, pool, upstream_path)
        return None

    @staticmethod
    def _matching_prefix(route: RouteConfig, path: str) -> str | None:
        """Prefixo que casou ("" quando a rota não filtra por path)."""
        if not route.path_prefixes:
            return ""
        for prefix in route.path_prefixes:
            # "/users" casa "/users" e "/users/1", mas não "/usersX"
            if prefix == "/" or path == prefix or path.startswith(prefix + "/"):
                return prefix
        return None

    def _choose_pool(self, route: RouteConfig, headers) -> str | None:
        if route.pool_from_header:
            pool = headers.get(route.pool_from_header)
            return pool if pool in self.pool_names else None
        if len(route.pools) == 1:
            return route.pools[0].pool
        # Divisão ponderada: com pesos 90/10, ~10% das requisições vão para o 2º pool.
        weights = [p.weight for p in route.pools]
        return self.rng.choices([p.pool for p in route.pools], weights=weights)[0]
