from app.circuit_breaker import CircuitBreaker
from app.upstream import Upstream


class FakeClock:
    """Relógio controlado pelo teste: `clock.now += 10` "espera" 10 segundos."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def upstreams(*names, clock=None):
    return [Upstream(n, f"http://{n}", CircuitBreaker(n, clock=clock or FakeClock())) for n in names]
