# Pendências — API Python

O que ainda falta para a API Python (e a infraestrutura comum) ficar pronta.

## Situação atual

| Arquivo | Situação |
|---|---|
| `db/Dockerfile` | ✅ pronto |
| `api-python/requirements.txt` | ✅ pronto |
| `api-python/app/db.py` | ✅ pronto |
| `api-python/app/errors.py` | ✅ pronto |
| `db/init.sql` | ⚠️ 1 bug |
| `api-python/app/schemas.py` | ⚠️ 2 bugs |
| `api-python/app/models.py` | ⚠️ 1 bug + 1 função repetida |
| `api-python/app/error_handlers.py` | ⚠️ 1 bug + incompleto |
| `api-python/app/routers/users.py` | ❌ vazio |
| `api-python/app/main.py` | ❌ vazio |
| `api-python/Dockerfile` | ❌ vazio |
| `api-python/.dockerignore` | ❌ vazio |
| `pgadmin/servers.json` | ❌ vazio |
| `docker-compose.yml` | ❌ vazio |
| `testes/requests.http` | ❌ vazio |
| `README.md` | ❌ vazio (colocar o contrato da API) |

---

## 1. Corrigir os arquivos já começados

### `db/init.sql`: nome da função diferente do nome usado no trigger

A função foi criada como `set_update_at`, mas o trigger chama `set_updated_at`. O Postgres para o script nesse erro e o container do banco não sobe.

```sql
-- errado
CREATE OR REPLACE FUNCTION set_update_at() RETURNS TRIGGER AS $$

-- certo
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
```

> Lembrete: o `init.sql` só roda com o volume vazio. Depois de corrigir, rode `docker compose down -v`.

### `api-python/app/schemas.py`: erro de digitação e falta um model

1. `min_lenght` → `min_length`. Com o nome errado, o Pydantic ignora a regra e aceita nome vazio.
2. `NovoUsuario` ficou com os campos opcionais, que são do `AtualizarUsuario`. No `NovoUsuario` todos os campos são obrigatórios, e o `AtualizarUsuario` está faltando.

Arquivo completo:

```python
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

Nome = Annotated[str, Field(min_length=1)]
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Cpf = Annotated[str, Field(pattern=r"^[0-9]{11}$")]


class NovoUsuario(BaseModel):
    name: Nome
    email: Email
    birthday: date
    cpf: Cpf


class AtualizarUsuario(BaseModel):
    name: Nome | None = None
    email: Email | None = None
    birthday: date | None = None
    cpf: Cpf | None = None


class Usuario(BaseModel):
    id: int
    name: str
    email: str
    birthday: str
    cpf: str
    inserted_at: str
    updated_at: str
```

### `api-python/app/models.py`: vírgula sobrando no SQL

Na constante `COLUNAS`, a linha do `inserted_at` tem uma vírgula antes do `AS`, e isso dá erro de sintaxe no SQL em **todas** as rotas:

```python
# errado
to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), AS inserted_at,

# certo
to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS inserted_at,
```

A função `buscar_por_id` também está escrita duas vezes. Apague uma delas. Isso não quebra nada, porque a segunda substitui a primeira, mas confunde quem lê.

### `api-python/app/error_handlers.py`: vírgula depois do `}` e falta o resto

A vírgula depois do `}` transforma o `CONFLITOS` numa **tupla** com um dicionário dentro, em vez de um dicionário. Então `CONFLITOS.get(...)` quebraria.

```python
# errado
CONFLITOS = {
    ...
},

# certo
CONFLITOS = {
    ...
}
```

Arquivo completo:

```python
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation

from app.errors import ApiError

logger = logging.getLogger("uvicorn.error")

# nome da constraint no banco (db/init.sql) -> erro devolvido pela API
CONFLITOS = {
    "users_email_key": ("EMAIL_IN_USE", "Este e-mail já está cadastrado."),
    "users_cpf_key": ("CPF_IN_USE", "Este CPF já está cadastrado."),
}


def erro(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def registrar_error_handlers(app):
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return erro(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        primeiro = exc.errors()[0]
        campo = primeiro["loc"][-1]
        if primeiro["type"] == "json_invalid" or campo == "body":
            return erro(400, "VALIDATION_ERROR", "Corpo da requisição ausente ou com JSON inválido.")
        return erro(400, "VALIDATION_ERROR", f"O campo '{campo}' é inválido ou está ausente.")

    @app.exception_handler(UniqueViolation)
    async def handle_unique_violation(request: Request, exc: UniqueViolation):
        code, message = CONFLITOS.get(
            exc.diag.constraint_name, ("CONFLICT", "Registro duplicado.")
        )
        return erro(409, code, message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("Erro não tratado")
        return erro(500, "INTERNAL_ERROR", "Erro interno do servidor.")
```

---

## 2. Arquivos que faltam

### `api-python/app/routers/users.py`

```python
from fastapi import APIRouter, Response

from app import models
from app.errors import ApiError
from app.schemas import AtualizarUsuario, NovoUsuario, Usuario

router = APIRouter(prefix="/users", tags=["Users"])


def nao_encontrado() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Usuário não encontrado.")


@router.post("", response_model=Usuario, status_code=201)
def criar(dados: NovoUsuario, response: Response):
    usuario = models.criar(dados.name, dados.email, dados.birthday, dados.cpf)
    response.headers["Location"] = f"/users/{usuario['id']}"
    return usuario


@router.get("", response_model=list[Usuario])
def listar():
    return models.listar()


@router.get("/{id}", response_model=Usuario)
def buscar(id: int):
    usuario = models.buscar_por_id(id)
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.put("/{id}", response_model=Usuario)
def substituir(id: int, dados: NovoUsuario):
    usuario = models.atualizar(id, dados.name, dados.email, dados.birthday, dados.cpf)
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.patch("/{id}", response_model=Usuario)
def atualizar_parcial(id: int, dados: AtualizarUsuario):
    usuario = models.atualizar_parcial(
        id, dados.name, dados.email, dados.birthday, dados.cpf
    )
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.delete("/{id}", status_code=204)
def remover(id: int):
    if not models.remover(id):
        raise nao_encontrado()
```

### `api-python/app/main.py`

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import pool
from app.error_handlers import registrar_error_handlers
from app.routers import users


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True)  # falha logo na subida se o banco não estiver acessível
    yield
    pool.close()


app = FastAPI(title="API de Usuários - Python", lifespan=lifespan)

app.include_router(users.router)

registrar_error_handlers(app)
```

### `api-python/Dockerfile`

```dockerfile
FROM python:3.13-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `api-python/.dockerignore`

```
venv/
__pycache__/
```

### `pgadmin/servers.json`

```json
{
  "Servers": {
    "1": {
      "Name": "Users DB",
      "Group": "Servers",
      "Host": "db",
      "Port": 5432,
      "MaintenanceDB": "users_db",
      "Username": "postgres",
      "SSLMode": "prefer"
    }
  }
}
```

### `docker-compose.yml`

```yaml
services:
  db:
    build: ./db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: users_db
    ports:
      - "5432:5432"
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d users_db"]
      interval: 5s
      timeout: 3s
      retries: 10

  pgadmin:
    image: dpage/pgadmin4
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    volumes:
      - ./pgadmin/servers.json:/pgadmin4/servers.json
    depends_on:
      - db

  api-python:
    build: ./api-python
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/users_db
    ports:
      - "8001:8000"
    depends_on:
      db:
        condition: service_healthy

  # api-node:  -> "8002:8000"
  # api-go:    -> "8003:8000"
  # api-rust:  -> "8004:8000"

volumes:
  db-data:
```

### `testes/requests.http`

Este arquivo usa a extensão REST Client do VS Code. Para testar outra API, troque só a porta em `@baseUrl`.

```http
@baseUrl = http://localhost:8001

### Criar
POST {{baseUrl}}/users
Content-Type: application/json

{ "name": "Ana Silva", "email": "ana@exemplo.com", "birthday": "2000-05-15", "cpf": "12345678901" }

### Listar
GET {{baseUrl}}/users

### Buscar
GET {{baseUrl}}/users/1

### Substituir
PUT {{baseUrl}}/users/1
Content-Type: application/json

{ "name": "Ana Souza", "email": "ana@exemplo.com", "birthday": "2000-05-15", "cpf": "12345678901" }

### Atualizar parcial
PATCH {{baseUrl}}/users/1
Content-Type: application/json

{ "name": "Ana S. Souza" }

### Remover
DELETE {{baseUrl}}/users/1
```

### `README.md`: o contrato da API

As 4 APIs têm que seguir exatamente este contrato.

| Método | Rota | Body | Sucesso | Erros |
|---|---|---|---|---|
| POST | `/users` | todos os campos | **201** + usuário + header `Location` | 400, 409 |
| GET | `/users` | — | **200** lista ordenada por id | — |
| GET | `/users/{id}` | — | **200** usuário | 400, 404 |
| PUT | `/users/{id}` | todos os campos | **200** usuário | 400, 404, 409 |
| PATCH | `/users/{id}` | só os campos que mudam | **200** usuário | 400, 404, 409 |
| DELETE | `/users/{id}` | — | **204** sem corpo | 400, 404 |

Regras dos campos:

- `name`: texto não vazio
- `email`: regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`
- `birthday`: `"YYYY-MM-DD"`
- `cpf`: string com 11 dígitos, só números

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

---

## 3. Rodando

Abra o Docker Desktop antes. Depois, na raiz do projeto:

```powershell
docker compose up --build
```

- Swagger da API: http://localhost:8001/docs
- pgAdmin: http://localhost:5050 (login `admin@admin.com` / `admin`). O servidor "Users DB" já aparece, e a senha dele é `postgres`.

Para desenvolver sem precisar rebuildar a cada mudança:

```powershell
docker compose up -d db pgadmin
cd api-python
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8001
```

---

## 4. Depois da API Python

Node (8002), Go (8003) e Rust (8004) seguem o mesmo contrato do README:

- Copie os SQLs do `models.py`, principalmente a constante `COLUNAS`. Assim as datas saem no mesmo formato nas 4 APIs.
- Use a mesma regex de e-mail e de CPF.
- Traduza o erro de UNIQUE do banco (constraints `users_email_key` e `users_cpf_key`) para 409.
- Descomente o serviço correspondente no `docker-compose.yml`.
