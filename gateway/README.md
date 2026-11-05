# gateway

API Gateway didático em Python 3.13 + aiohttp, na frente das 4 APIs de
CRUD de usuários (Python, Node, Go e Rust). Cada conceito está em um arquivo
pequeno e comentado.

```
cliente ──► gateway :8080 ──► api-python | api-node | api-go | api-rust ──► PostgreSQL
```

## Onde está cada coisa

| Conceito | Arquivo | Em uma frase |
|---|---|---|
| Pipeline | [`app/gateway.py`](app/gateway.py) | A ordem dos passos de uma requisição. **Comece por aqui.** |
| Reverse proxy | [`app/proxy.py`](app/proxy.py) | Repassa a requisição, remove headers hop-by-hop e adiciona `X-Forwarded-*`. |
| Traffic routing | [`app/routing.py`](app/routing.py) | Escolhe o **pool** pelo path, header ou peso (canary). |
| Load balancing | [`app/balancers/`](app/balancers) | Escolhe o **upstream** dentro do pool. Um arquivo por algoritmo. |
| Circuit breaker | [`app/circuit_breaker.py`](app/circuit_breaker.py) | Para de mandar tráfego para quem está falhando (passivo). |
| Health check | [`app/health.py`](app/health.py) | Pergunta `/health` a cada N segundos (ativo). |
| Rate limit | [`app/rate_limit.py`](app/rate_limit.py) | Token bucket por IP de cliente → `429`. |
| Cache | [`app/cache.py`](app/cache.py) | Guarda `GET 200` por alguns segundos e invalida na escrita. |
| Configuração | [`gateway.yaml`](gateway.yaml) | Upstreams, pools, rotas e limites. Aceita `${VAR:-default}`. |
| Admin | [`app/admin.py`](app/admin.py) | `/_gateway/status`, `/_gateway/health`, `POST /_gateway/cache/flush`. |

O caminho de uma requisição (`app/gateway.py`):

```
1. rate limit ......... passou do limite? -> 429 RATE_LIMITED
2. traffic routing .... nenhuma rota casa? -> 404 NOT_FOUND
3. cache .............. GET já está no cache? -> responde (X-Cache: HIT)
4. load balancing ..... escolhe um upstream saudável e com circuito fechado
5. reverse proxy ...... repassa; se a conexão falhar, tenta OUTRO (retry, só métodos idempotentes)
6. circuit breaker .... anota sucesso/falha do upstream
7. cache .............. guarda o GET 200 / invalida em POST, PUT, PATCH e DELETE
```

Todos os erros do gateway usam o mesmo formato de erro das APIs,
`{ "error": { "code": "...", "message": "..." } }`, então o cliente não precisa
saber se o erro veio do gateway ou de um upstream. Respostas de sucesso não têm
envelope: o corpo do upstream é repassado como veio (o mesmo vale para o JSON
de `/_gateway/*`).

| Status | `code` | `message` | Quando |
|---|---|---|---|
| 404 | `NOT_FOUND` | `Rota não encontrada.` | nenhuma rota do `gateway.yaml` casou |
| 429 | `RATE_LIMITED` | `Limite de requisições excedido.` | o balde do cliente esvaziou (veja `Retry-After`) |
| 502 | `BAD_GATEWAY` | `Nenhum upstream respondeu.` | não deu para conectar no upstream (nem no retry) |
| 503 | `NO_UPSTREAM_AVAILABLE` | `Nenhum upstream disponível.` | todos os upstreams do pool estão fora ou com o circuito aberto |
| 504 | `GATEWAY_TIMEOUT` | `O upstream demorou demais para responder.` | o upstream demorou mais que `PROXY_TIMEOUT_SECONDS` |

Headers que o gateway acrescenta na resposta: `X-Upstream` (quem atendeu),
`X-Gateway-Route`, `X-Gateway-Pool`, `X-Gateway-Strategy`, `X-Cache`
(`HIT`/`MISS`/`BYPASS`), `X-Request-Id`, `X-RateLimit-Limit` e `X-RateLimit-Remaining`.

## Algoritmos de load balancing

Escolhidos por `LB_STRATEGY` (vale para os pools `all`, `compiled` e `dynamic`).

| `LB_STRATEGY` | Como escolhe | Bom para | Cuidado |
|---|---|---|---|
| `round_robin` (padrão) | um de cada vez, em fila | servidores iguais, requisições parecidas | ignora carga e lentidão |
| `sticky_round_robin` | round-robin na 1ª vez, depois o cookie `gw_sticky_<pool>` fixa o servidor | estado em memória (sessão) | carga desigual se poucos clientes fazem muito |
| `least_connections` | menos requisições em andamento | requisições de duração variada | com pouco tráfego, todos têm 0 (desempate aleatório) |
| `least_time` | menor `latência média × (conexões + 1)` | servidores com velocidades diferentes | com tráfego sequencial, quase tudo vai para o mais rápido |
| `ip_hash` | `md5(ip) % N` | afinidade sem cookie | muitos clientes atrás do mesmo NAT caem juntos |
| `random_two_choices` | sorteia 2, fica com o de menos conexões | muitos gateways/servidores | — |

## Configuração por variável de ambiente

Os defaults ficam no [`gateway.yaml`](gateway.yaml); o `docker compose` repassa
estas variáveis do seu shell. Para trocar, recrie o gateway:

```bash
LB_STRATEGY=least_connections docker compose up -d gateway
```

No PowerShell: `$env:LB_STRATEGY="least_connections"; docker compose up -d gateway`.

| Variável | Default | |
|---|---|---|
| `LB_STRATEGY` | `round_robin` | algoritmo dos pools `all`, `compiled`, `dynamic` |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_BURST` | `200` | tamanho do balde (rajada máxima) |
| `RATE_LIMIT_RPS` | `100` | fichas repostas por segundo |
| `CACHE_ENABLED` | `true` | |
| `CACHE_TTL_SECONDS` | `5` | |
| `CB_FAILURE_THRESHOLD` | `3` | falhas seguidas para abrir o circuito |
| `CB_OPEN_SECONDS` | `10` | tempo aberto até a requisição de teste |
| `HEALTH_CHECK_ENABLED` | `true` | |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `5` | |
| `PROXY_TIMEOUT_SECONDS` | `5` | |
| `PROXY_RETRIES` | `1` | quantos upstreams extras tentar (só GET/PUT/DELETE; POST e PATCH não são repetidos) |
| `CANARY_WEIGHT` / `CANARY_STABLE_WEIGHT` | `10` / `90` | divisão da rota `/canary` |
| `API_<NOME>_LATENCY_MS` (ex. `API_RUST_LATENCY_MS`) | `0` | **simulação**: atraso artificial antes de repassar |

## Roteiro de experimentos

Suba tudo com `docker compose up -d --build` e deixe `docker compose logs -f gateway`
rodando em outro terminal. Cada requisição gera uma linha de log com o upstream
que atendeu, o status, o tempo, a rota e o estado do cache.

Para disparar várias requisições e ver quem atendeu cada uma (Git Bash):

```bash
for i in $(seq 12); do curl -si localhost:8080/users -H 'Cache-Control: no-cache' | grep -i x-upstream; done
```

No PowerShell:

```powershell
1..12 | % { curl.exe -si localhost:8080/users -H "Cache-Control: no-cache" | Select-String "x-upstream" }
```

(O `Cache-Control: no-cache` evita que o cache responda no lugar dos upstreams.)

**1. Reverse proxy.** O cliente não sabe quem atendeu: o contrato da API é o
mesmo com ou sem o gateway.

```bash
curl -i localhost:8080/users        # veja X-Upstream, X-Request-Id, X-Gateway-*
```

**2. Round-robin.** Rode o laço acima: as 4 APIs se revezam, em ordem.

**3. Traffic routing.**

```bash
curl -i localhost:8080/rust/users                     # por path (a api-rust recebe /users)
curl -i -H 'X-Backend: api-go' localhost:8080/users   # por header
curl -i localhost:8080/canary/users                   # canary: ~90% compiled (Go, Rust), ~10% dynamic (Python, Node)
curl -i localhost:8080/qualquer-coisa                 # 404 NOT_FOUND, sem chegar nos upstreams
```

**4. Sticky round-robin.**

```bash
LB_STRATEGY=sticky_round_robin docker compose up -d gateway
curl -i -c /tmp/c -b /tmp/c localhost:8080/users   # repita: sempre o mesmo upstream (Set-Cookie na 1ª)
curl -i localhost:8080/users                       # sem cookie: continua girando
```

**5. IP hash.**

```bash
LB_STRATEGY=ip_hash docker compose up -d gateway
curl -si -H 'X-Forwarded-For: 10.0.0.1' localhost:8080/users | grep -i x-upstream   # sempre o mesmo
curl -si -H 'X-Forwarded-For: 10.0.0.2' localhost:8080/users | grep -i x-upstream   # outro (talvez o mesmo, é hash)
```

**6. Least time e least connections.** Deixe uma API lenta de propósito:

```bash
LB_STRATEGY=least_time API_RUST_LATENCY_MS=300 docker compose up -d gateway
# rode o laço: a api-rust é testada uma vez e depois evitada
LB_STRATEGY=round_robin API_RUST_LATENCY_MS=300 docker compose up -d gateway
# rode o laço: round-robin não liga, 1 a cada 4 fica lenta
```

Para `least_connections` e `random_two_choices`, dispare requisições em paralelo
(por exemplo com `xargs -P 20`, `hey` ou `k6`): o servidor lento acumula conexões
abertas e passa a receber menos.

**7. Circuit breaker e health check.**

```bash
docker compose stop api-rust
# rode o laço: todas 200, o retry esconde a queda; nos logs: CLOSED -> OPEN;
# depois o health check marca a api-rust como DOWN
docker compose start api-rust
# o health check marca UP; a próxima requisição de teste fecha o circuito
curl -s localhost:8080/_gateway/status      # estado dos circuitos e dos health checks
```

Num pool com um upstream só não há para onde fazer retry: com a api-rust
parada, repetir `curl -i localhost:8080/rust/users` dá `502 BAD_GATEWAY` até o
circuito abrir e depois `503 NO_UPSTREAM_AVAILABLE` (sem nem tentar conectar).

O health check usa o `GET /health` das APIs, que responde `503` quando o banco
está fora: com `docker compose stop db`, as 4 APIs são marcadas como DOWN.

**8. Rate limit.**

```bash
RATE_LIMIT_BURST=5 RATE_LIMIT_RPS=1 docker compose up -d gateway
for i in $(seq 10); do curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/users; done   # ~5 passam, o resto é 429
curl -i localhost:8080/users                                  # veja Retry-After e X-RateLimit-Remaining
curl -i -H 'X-Forwarded-For: 10.0.0.99' localhost:8080/users  # outro cliente tem o próprio balde
```

Nos logs, cada bloqueio aparece como `WARNING ... BLOQUEADA pelo rate limit (429)`.

**9. Cache.**

```bash
curl -si localhost:8080/users | grep -i -E 'x-cache|x-upstream|age'   # MISS
curl -si localhost:8080/users | grep -i -E 'x-cache|x-upstream|age'   # HIT (mesmo upstream, sem ir até ele)
curl -s -X POST localhost:8080/users -H 'content-type: application/json' \
  -d '{"name":"Ada","email":"ada@exemplo.com","birthday":"1990-01-01","cpf":"12345678901"}'
curl -si localhost:8080/users | grep -i x-cache                       # MISS: a escrita invalidou
curl -si localhost:8080/users -H 'Cache-Control: no-cache' | grep -i x-cache   # BYPASS
curl -s -X POST localhost:8080/_gateway/cache/flush                   # esvazia o cache: {"removed": N}
```

(Repetir o POST com o mesmo e-mail/CPF dá `409`: troque os valores.)

Nos logs, o HIT aparece como `CACHE HIT (de api-go)`: o upstream entre parênteses
é quem gerou a resposta guardada, não quem atendeu agora.

## Para discutir em aula

- O estado (contadores, baldes, cache, circuitos) vive na memória de **um**
  processo. Com várias réplicas do gateway, cada uma tem o seu; em produção
  isso vai para um Redis, por exemplo.
- `least_time` nunca mais testa um servidor que foi lento uma vez se os outros
  continuam rápidos. Gateways reais misturam um pouco de aleatoriedade ou
  "esquecem" medições antigas.
- `ip_hash` com `% N` remapeia quase todo mundo quando N muda (servidor novo).
  Consistent hashing resolve isso.
- `X-Forwarded-For` só é confiável vindo de um proxy conhecido. Aqui
  `trust_forwarded_for: true` serve para simular clientes.

## Rodando fora do Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                      # testes (upstreams falsos, não precisa das APIs)
API_PYTHON_URL=http://localhost:8001 API_NODE_URL=http://localhost:8002 \
API_GO_URL=http://localhost:8003 API_RUST_URL=http://localhost:8004 \
PORT=8090 python -m app.main
```
