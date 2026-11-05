"""Upstream: um servidor de verdade atrás do gateway, e as métricas que os
algoritmos de load balancing usam para decidir."""

from .circuit_breaker import CircuitBreaker

# Peso da medição mais recente na média móvel exponencial (EWMA) da latência.
# 0.3 = reage rápido a mudanças, mas não "pula" a cada requisição lenta isolada.
EWMA_ALPHA = 0.3


class Upstream:
    def __init__(self, name: str, url: str, breaker: CircuitBreaker, simulate_latency_ms: int = 0):
        self.name = name
        self.url = url
        self.breaker = breaker
        self.simulate_latency_ms = simulate_latency_ms

        self.healthy = True  # atualizado pelo health check ativo (health.py)
        self.active_connections = 0  # requisições em andamento agora (least_connections)
        self.latency_ewma_ms: float | None = None  # tempo médio de resposta (least_time)
        self.requests = 0
        self.errors = 0

    def available(self) -> bool:
        """Pode receber tráfego: está saudável E o circuit breaker deixa."""
        return self.healthy and self.breaker.allows_request()

    def record_latency(self, ms: float) -> None:
        if self.latency_ewma_ms is None:
            self.latency_ewma_ms = ms
        else:
            self.latency_ewma_ms = EWMA_ALPHA * ms + (1 - EWMA_ALPHA) * self.latency_ewma_ms

    def __repr__(self) -> str:
        return f"Upstream({self.name})"
