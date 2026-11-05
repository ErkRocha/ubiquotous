# CRUD de Usuários em 4 linguagens

4 APIs REST (Python, Node, Go e Rust) com **os mesmos endpoints, requests e responses**, todas usando o mesmo PostgreSQL.

| Serviço | Pasta | Tecnologia | Porta |
|---|---|---|---|
| API Python | `api-python/` | FastAPI + psycopg | http://localhost:8001 |
| API Node | `api-node/` | Express + pg | http://localhost:8002 |
| API Go | `api-go/` | net/http + pgx | http://localhost:8003 |
| API Rust | `api-rust/` | axum + tokio-postgres | http://localhost:8004 |
| API Gateway | `gateway/` | Python + aiohttp | http://localhost:8080 |
| PostgreSQL | `db/` | Postgres 17 | localhost:5432 |
| pgAdmin | `pgadmin/` | pgAdmin 4 | http://localhost:5050 |

## Rodando

Com o Docker Desktop aberto, na raiz do projeto:

```powershell
docker compose up --build
```

- pgAdmin: http://localhost:5050 (login `admin@admin.com` / `admin`). O servidor "Users DB" já aparece; a senha dele é `postgres`.
- Swagger da API Python: http://localhost:8001/docs
- Gateway: http://localhost:8080 (veja a seção "API Gateway" abaixo).
- Requisições de exemplo: `testes/requests.http` (extensão REST Client do VS Code).

> O `db/init.sql` só roda com o volume vazio. Se mudar o SQL, rode `docker compose down -v`.

## Contrato da API

| Método | Rota | Body | Sucesso | Erros |
|---|---|---|---|---|
| POST | `/users` | todos os campos | **201** + usuário + header `Location` | 400, 409 |
| GET | `/users` | — | **200** lista ordenada por id | — |
| GET | `/users/{id}` | — | **200** usuário | 400, 404 |
| PUT | `/users/{id}` | todos os campos | **200** usuário | 400, 404, 409 |
| PATCH | `/users/{id}` | só os campos que mudam | **200** usuário | 400, 404, 409 |
| DELETE | `/users/{id}` | — | **204** sem corpo | 400, 404 |
| GET | `/health` | — | **200** `{"status":"ok","database":"up"}` | **503** `{"status":"error","database":"down"}` se o banco estiver fora |

Regras dos campos:

- `name`: texto não vazio
- `email`: regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`
- `birthday`: `"YYYY-MM-DD"` (data válida)
- `cpf`: string com 11 dígitos, só números

Request (POST/PUT):

```json
{ "name": "Ana Silva", "email": "ana@exemplo.com", "birthday": "2000-05-15", "cpf": "12345678901" }
```

Resposta (sempre nesta ordem de campos):

```json
{
  "id": 1,
  "name": "Ana Silva",
  "email": "ana@exemplo.com",
  "birthday": "2000-05-15",
  "cpf": "12345678901",
  "inserted_at": "2026-10-22T12:32:51Z",
  "updated_at": "2026-10-22T12:32:51Z"
}
```

Erros, sempre no formato `{ "error": { "code": "...", "message": "..." } }`:

| HTTP | code | message |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `O campo '<campo>' é inválido ou está ausente.` ou `Corpo da requisição ausente ou com JSON inválido.` |
| 404 | `NOT_FOUND` | `Usuário não encontrado.` |
| 409 | `EMAIL_IN_USE` | `Este e-mail já está cadastrado.` |
| 409 | `CPF_IN_USE` | `Este CPF já está cadastrado.` |
| 500 | `INTERNAL_ERROR` | `Erro interno do servidor.` |

Detalhes que as 4 APIs seguem igual:

- Os campos são validados na ordem `name`, `email`, `birthday`, `cpf`; o erro aponta o primeiro inválido.
- No PATCH, campo ausente ou `null` não é alterado.
- As datas são formatadas pelo próprio Postgres (`to_char`) no SQL, para sair no mesmo formato em todas.
- `updated_at` é atualizado por um trigger no banco.
- O 409 vem da constraint UNIQUE do banco (`users_email_key`, `users_cpf_key`).

## API Gateway

O `gateway/` é um API Gateway didático (Python + aiohttp) na frente das 4 APIs. Os clientes devem falar com **http://localhost:8080**; as portas 8001 a 8004 continuam abertas para testar cada API direto.

```powershell
curl -i localhost:8080/users
```

Funcionalidades:

- **Reverse proxy**: repassa a requisição ao upstream e devolve a resposta como veio.
- **Traffic routing**: escolhe o pool por header (`X-Backend: api-rust`), por path (`/python`, `/node`, `/go`, `/rust`) ou por peso (`/canary`, 90% Go/Rust e 10% Python/Node).
- **Load balancing** com 6 estratégias (`LB_STRATEGY`): `round_robin`, `sticky_round_robin`, `least_connections`, `least_time`, `ip_hash` e `random_two_choices`.
- **Circuit breaker**: para de mandar tráfego a um upstream que falha seguidamente.
- **Health check**: consulta o `GET /health` de cada API a cada poucos segundos.
- **Rate limit**: token bucket por IP de cliente.
- **Cache** de `GET` com invalidação em `POST`, `PUT`, `PATCH` e `DELETE`.

Headers que o gateway acrescenta na resposta: `X-Upstream` (qual API atendeu), `X-Cache` (`HIT`/`MISS`/`BYPASS`), `X-Request-Id`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` e `X-Gateway-Route`/`X-Gateway-Pool`/`X-Gateway-Strategy`.

Erros do próprio gateway, no mesmo formato das APIs:

| HTTP | code | message |
|---|---|---|
| 404 | `NOT_FOUND` | `Rota não encontrada.` |
| 429 | `RATE_LIMITED` | `Limite de requisições excedido.` |
| 502 | `BAD_GATEWAY` | `Nenhum upstream respondeu.` |
| 503 | `NO_UPSTREAM_AVAILABLE` | `Nenhum upstream disponível.` |
| 504 | `GATEWAY_TIMEOUT` | `O upstream demorou demais para responder.` |

Endpoints do próprio gateway: `GET /_gateway/health`, `GET /_gateway/status` e `POST /_gateway/cache/flush`.

Para trocar o algoritmo e outros parâmetros: `LB_STRATEGY=ip_hash docker compose up -d gateway` (no PowerShell: `$env:LB_STRATEGY="ip_hash"; docker compose up -d gateway`). Detalhes, variáveis e roteiro de experimentos em [gateway/README.md](gateway/README.md).
