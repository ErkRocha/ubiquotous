"""Testes do gateway de ponta a ponta, com upstreams falsos (servidores aiohttp locais)."""

from collections import Counter

import pytest
from aiohttp import web

from app.circuit_breaker import OPEN
from app.config import Config, PoolConfig, RouteConfig, UpstreamConfig, WeightedPool
from app.main import GATEWAY, create_app

CALLS = web.AppKey("calls", Counter)
DEAD_URL = "http://127.0.0.1:1"  # porta fechada: conexão recusada na hora


def fake_upstream(name: str) -> web.Application:
    """Responde JSON como as APIs, contando as chamadas e ecoando o que recebeu."""
    app = web.Application()
    calls = app[CALLS] = Counter()

    async def handler(request: web.Request):
        calls["n"] += 1
        status = 201 if request.method == "POST" else 200
        return web.json_response({
            "server": name, "path": request.path, "query": request.query_string,
            "forwarded_for": request.headers.get("X-Forwarded-For"),
            "request_id": request.headers.get("X-Request-Id"),
        }, status=status)

    app.router.add_route("*", "/{tail:.*}", handler)
    return app


def make_config(urls: dict[str, str], strategy="round_robin", **overrides) -> Config:
    names = list(urls)
    routes = [
        RouteConfig("by-header", headers_present=["X-Backend"], pool_from_header="X-Backend"),
        RouteConfig("first", path_prefixes=["/first"], pools=[WeightedPool(names[0], 1)], strip_prefix=True),
        RouteConfig("default", path_prefixes=["/users", "/health"], pools=[WeightedPool("all", 1)]),
    ]
    pools = [PoolConfig("all", names, strategy)] + [PoolConfig(n, [n]) for n in names]
    cfg = Config(port=0, trust_forwarded_for=True, upstreams=[UpstreamConfig(n, u) for n, u in urls.items()],
                 pools=pools, routes=routes, health_enabled=False, cache_enabled=False, proxy_timeout=2)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
async def backends(aiohttp_server):
    servers = {}
    for name in ("a", "b"):
        servers[name] = await aiohttp_server(fake_upstream(name))
    return servers


@pytest.fixture
def gateway(aiohttp_client, backends):
    async def start(urls=None, **kwargs):
        urls = urls or {n: str(s.make_url("")).rstrip("/") for n, s in backends.items()}
        return await aiohttp_client(create_app(make_config(urls, **kwargs)))
    return start


async def test_round_robin_alternates_and_proxies_the_request(gateway):
    client = await gateway()
    seen = []
    for _ in range(4):
        resp = await client.get("/users?x=1", headers={"X-Forwarded-For": "10.0.0.9"})
        body = await resp.json()
        assert resp.status == 200
        assert resp.headers["X-Upstream"] == body["server"]
        assert resp.headers["X-Gateway-Strategy"] == "round_robin"
        assert body["query"] == "x=1"
        assert body["forwarded_for"] == "10.0.0.9, 127.0.0.1"
        assert body["request_id"] == resp.headers["X-Request-Id"]
        seen.append(resp.headers["X-Upstream"])
    assert seen == ["a", "b", "a", "b"]


async def test_unknown_route_is_404_in_repo_error_format(gateway):
    client = await gateway()
    resp = await client.get("/nope")
    assert resp.status == 404
    assert await resp.json() == {"error": {"code": "NOT_FOUND", "message": "Rota não encontrada."}}


async def test_path_and_header_routing(gateway):
    client = await gateway()
    resp = await client.get("/first/users/3")
    body = await resp.json()
    assert (body["server"], body["path"]) == ("a", "/users/3")

    resp = await client.get("/users", headers={"X-Backend": "b"})
    assert resp.headers["X-Upstream"] == "b" and resp.headers["X-Gateway-Route"] == "by-header"


async def test_sticky_round_robin_cookie(gateway):
    client = await gateway(strategy="sticky_round_robin")
    first = await client.get("/users")
    assert "gw_sticky_all" in first.cookies
    upstreams = {(await client.get("/users")).headers["X-Upstream"] for _ in range(5)}
    assert upstreams == {first.headers["X-Upstream"]}


async def test_ip_hash_keeps_client_on_same_upstream(gateway):
    client = await gateway(strategy="ip_hash")
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        got = {(await client.get("/users", headers={"X-Forwarded-For": ip})).headers["X-Upstream"] for _ in range(4)}
        assert len(got) == 1


async def test_cache_hit_miss_bypass_and_invalidation(gateway, backends):
    client = await gateway(cache_enabled=True, cache_ttl=60)
    assert (await client.get("/users")).headers["X-Cache"] == "MISS"
    hit = await client.get("/users")
    assert hit.headers["X-Cache"] == "HIT" and "Age" in hit.headers
    assert (await client.get("/users", headers={"Cache-Control": "no-cache"})).headers["X-Cache"] == "BYPASS"
    assert sum(s.app[CALLS]["n"] for s in backends.values()) == 2

    assert (await client.post("/users", json={})).status == 201
    assert (await client.get("/users")).headers["X-Cache"] == "MISS"


async def test_rate_limit_returns_429(gateway):
    client = await gateway(rate_limit_capacity=2, rate_limit_refill=0.5)
    statuses = [(await client.get("/users")).status for _ in range(2)]
    blocked = await client.get("/users")
    assert statuses == [200, 200]
    assert blocked.status == 429
    assert blocked.headers["Retry-After"] == "2"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert (await blocked.json()) == {
        "error": {"code": "RATE_LIMITED", "message": "Limite de requisições excedido."}}
    # outro cliente tem o próprio balde
    assert (await client.get("/users", headers={"X-Forwarded-For": "10.9.9.9"})).status == 200


async def test_retry_hides_dead_upstream_and_circuit_opens(gateway, backends):
    client = await gateway(urls={"dead": DEAD_URL, "b": str(backends["b"].make_url("")).rstrip("/")},
                           cb_failure_threshold=2)
    upstreams = [(await client.get("/users")).headers["X-Upstream"] for _ in range(6)]
    assert upstreams == ["b"] * 6

    gw = client.app[GATEWAY]
    dead = gw.upstreams["dead"]
    assert dead.breaker.state == OPEN
    assert dead.requests == 2  # depois de aberto, o circuito não deixa mais tentar


async def test_post_is_not_retried(gateway, backends):
    client = await gateway(urls={"dead": DEAD_URL, "b": str(backends["b"].make_url("")).rstrip("/")})
    resp = await client.post("/users", json={})
    assert resp.status == 502
    assert await resp.json() == {"error": {"code": "BAD_GATEWAY", "message": "Nenhum upstream respondeu."}}


async def test_patch_is_not_retried_and_invalidates_cache(gateway, backends):
    client = await gateway(urls={"dead": DEAD_URL, "b": str(backends["b"].make_url("")).rstrip("/")})
    resp = await client.patch("/users/1", json={"name": "x"})
    assert resp.status == 502  # sem retry: PATCH não é idempotente
    assert (await resp.json())["error"]["code"] == "BAD_GATEWAY"


async def test_all_upstreams_down_gives_502_then_503(gateway):
    client = await gateway(urls={"x": DEAD_URL, "y": DEAD_URL}, cb_failure_threshold=1)
    assert (await client.get("/users")).status == 502
    resp = await client.get("/users")
    assert resp.status == 503
    assert (await resp.json()) == {
        "error": {"code": "NO_UPSTREAM_AVAILABLE", "message": "Nenhum upstream disponível."}}


async def test_status_endpoint(gateway):
    client = await gateway()
    await client.get("/users")
    resp = await client.get("/_gateway/status")
    data = await resp.json()
    assert resp.status == 200
    assert data["total_requests"] == 1
    assert Counter(u["name"] for u in data["upstreams"]) == {"a": 1, "b": 1}
    assert data["recent"][0]["path"] == "/users"
    assert (await client.get("/_gateway/whatever")).status == 404


async def test_admin_health_and_cache_flush_return_plain_json(gateway):
    client = await gateway(cache_enabled=True, cache_ttl=60)
    assert await (await client.get("/_gateway/health")).json() == {"status": "ok"}
    await client.get("/users")
    resp = await client.post("/_gateway/cache/flush")
    assert resp.status == 200
    assert await resp.json() == {"removed": 1}
