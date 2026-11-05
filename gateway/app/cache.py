"""Cache de respostas em memória, com TTL.

- Só guarda GET com status 200 (o resto pode ter efeito colateral ou ser erro).
- A chave inclui o pool: /rust/users e /go/users são entradas diferentes.
- Expira depois de `ttl_seconds`: durante esse tempo o cliente pode ver um dado
  "velho". Esse é o preço do cache; TTL curto = dado mais fresco, menos HITs.
- Escrita (POST/PUT/DELETE) em /users/... apaga todas as entradas de /users:
  o próximo GET busca o dado novo no upstream (invalidação).
- O cliente pode pular o cache mandando `Cache-Control: no-cache`.

Cabeçalho X-Cache na resposta: HIT (veio do cache), MISS (foi ao upstream e
guardou), BYPASS (não usou o cache).
"""

import time
from dataclasses import dataclass


@dataclass
class CachedResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    path: str
    stored_at: float
    expires_at: float


class ResponseCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 1000, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self.entries: dict[str, CachedResponse] = {}
        self.hits = 0
        self.misses = 0
        self.bypasses = 0

    @staticmethod
    def key(pool: str, path: str, query: str) -> str:
        return f"{pool} GET {path}?{query}" if query else f"{pool} GET {path}"

    def get(self, key: str) -> CachedResponse | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        if self.clock() >= entry.expires_at:
            del self.entries[key]
            return None
        return entry

    def age(self, entry: CachedResponse) -> int:
        return int(self.clock() - entry.stored_at)

    def put(self, key: str, path: str, status: int, headers: dict[str, str], body: bytes) -> None:
        now = self.clock()
        self.entries.pop(key, None)
        self.entries[key] = CachedResponse(status, headers, body, path, now, now + self.ttl)
        while len(self.entries) > self.max_entries:
            del self.entries[next(iter(self.entries))]  # remove a mais antiga

    def invalidate(self, path: str) -> int:
        """Apaga as entradas do mesmo recurso: escrita em /users/7 apaga /users e /users/*."""
        resource = "/" + path.strip("/").split("/")[0]
        stale = [k for k, e in self.entries.items() if e.path == resource or e.path.startswith(resource + "/")]
        for k in stale:
            del self.entries[k]
        return len(stale)

    def clear(self) -> None:
        self.entries.clear()
