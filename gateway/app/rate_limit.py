"""Rate limit com token bucket (balde de fichas), um balde por cliente.

- O balde comporta até `capacity` fichas e começa cheio.
- Entram `refill_per_second` fichas por segundo, até encher.
- Cada requisição gasta 1 ficha. Balde vazio => 429 Too Many Requests.

Resultado: o cliente pode fazer uma RAJADA de até `capacity` requisições, mas
na média não passa de `refill_per_second` por segundo.

Em vez de um timer enchendo os baldes, a reposição é calculada na hora:
fichas += tempo_desde_a_última_vez × refill_per_second.

Este estado fica na memória do processo: com vários gateways, cada um teria o
seu limite. Em produção o contador costuma ficar num Redis compartilhado.
"""

import math
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # segundos até ter 1 ficha (só quando bloqueado)


class TokenBucketLimiter:
    MAX_CLIENTS = 10_000

    def __init__(self, capacity: int, refill_per_second: float, clock=time.monotonic):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.clock = clock
        self.buckets: dict[str, tuple[float, float]] = {}  # cliente -> (fichas, último acesso)
        self.rejected = 0

    def check(self, client: str) -> Decision:
        now = self.clock()
        tokens, last = self.buckets.get(client, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)

        if tokens >= 1:
            tokens -= 1
            allowed, retry_after = True, 0
        else:
            allowed = False
            retry_after = math.ceil((1 - tokens) / self.refill_per_second)
            self.rejected += 1

        self.buckets[client] = (tokens, now)
        self._forget_idle_clients()
        return Decision(allowed, self.capacity, int(tokens), retry_after)

    def _forget_idle_clients(self) -> None:
        # Evita crescer sem limite: descarta os clientes mais antigos.
        while len(self.buckets) > self.MAX_CLIENTS:
            del self.buckets[next(iter(self.buckets))]
