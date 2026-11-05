"""Circuit breaker: para de mandar tráfego para um upstream que está falhando.

Máquina de estados (um breaker por upstream):

    CLOSED ──(N falhas seguidas)──> OPEN ──(passou open_seconds)──> HALF_OPEN
      ^                                ^                                 │
      │                                └──────(teste falhou)─────────────┤
      └───────────────────────────────────────(teste deu certo)──────────┘

- CLOSED: tudo normal, as requisições passam. Cada falha soma 1; um sucesso zera.
- OPEN: o upstream é ignorado pelo load balancer. Não adianta insistir em quem
  está caindo: só gera timeout para o cliente e mais carga para quem já sofre.
- HALF_OPEN: deixa passar UMA requisição de teste. Se der certo, fecha; se não,
  abre de novo por mais open_seconds.

A diferença para o health check (health.py) é que o breaker é PASSIVO: ele
aprende com o tráfego real, sem fazer requisições próprias.
"""

import logging
import time

log = logging.getLogger("gateway.circuit")

CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, open_seconds: float = 10, clock=time.monotonic):
        self.name = name
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.clock = clock  # injetável para os testes não precisarem esperar
        self._state = CLOSED
        self.failures = 0
        self.opened_at = 0.0
        self.trial_in_flight = False

    @property
    def state(self) -> str:
        # A passagem OPEN -> HALF_OPEN é "preguiçosa": acontece quando alguém
        # olha o estado depois que o tempo passou. Não precisa de timer.
        if self._state == OPEN and self.clock() - self.opened_at >= self.open_seconds:
            self._transition(HALF_OPEN)
        return self._state

    def allows_request(self) -> bool:
        """O load balancer pode escolher este upstream agora?"""
        state = self.state
        return state == CLOSED or (state == HALF_OPEN and not self.trial_in_flight)

    def before_request(self) -> None:
        """Chamado quando o upstream foi escolhido e a requisição vai sair."""
        if self.state == HALF_OPEN:
            self.trial_in_flight = True

    def record_success(self) -> None:
        self.failures = 0
        self.trial_in_flight = False
        if self._state != CLOSED:
            self._transition(CLOSED)

    def record_failure(self) -> None:
        self.trial_in_flight = False
        if self._state == HALF_OPEN:
            self._open()
            return
        self.failures += 1
        if self._state == CLOSED and self.failures >= self.failure_threshold:
            self._open()

    def retry_in(self) -> float:
        """Segundos até o circuito aberto liberar uma requisição de teste."""
        if self.state != OPEN:
            return 0
        return max(0.0, self.open_seconds - (self.clock() - self.opened_at))

    def _open(self) -> None:
        self.opened_at = self.clock()
        self._transition(OPEN)

    def _transition(self, new_state: str) -> None:
        log.warning("circuit %s: %s -> %s (falhas seguidas: %d)", self.name, self._state, new_state, self.failures)
        self._state = new_state
        if new_state == CLOSED:
            self.failures = 0
