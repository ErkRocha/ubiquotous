import random
from collections import Counter
from pathlib import Path

from multidict import CIMultiDict

from app import config
from app.balancers import STRATEGIES
from app.config import RouteConfig, WeightedPool
from app.routing import Router

GATEWAY_YAML = (Path(__file__).parent.parent / "gateway.yaml").read_text()


def test_expand_env_uses_value_or_default():
    assert config.expand_env("${A:-1} ${B:-2} ${C} ${D:-4}", {"A": "x", "D": ""}) == "x 2  4"


def test_gateway_yaml_defaults():
    cfg = config.parse(GATEWAY_YAML, env={})
    assert cfg.port == 8080
    assert cfg.trust_forwarded_for is True
    assert [u.name for u in cfg.upstreams]== ["api-python", "api-node", "api-go", "api-rust"]
    assert all(p.strategy in STRATEGIES for p in cfg.pools)
    assert cfg.rate_limit_capacity == 200 and cfg.cache_ttl == 5


def test_gateway_yaml_env_overrides():
    cfg = config.parse(GATEWAY_YAML, env={
        "LB_STRATEGY": "ip_hash", "CACHE_ENABLED": "false", "RATE_LIMIT_RPS": "2", "API_RUST_LATENCY_MS": "200",
    })
    assert next(p for p in cfg.pools if p.name == "all").strategy == "ip_hash"
    assert cfg.cache_enabled is False
    assert cfg.rate_limit_refill == 2
    assert next(u for u in cfg.upstreams if u.name == "api-rust").simulate_latency_ms == 200


def router():
    cfg = config.parse(GATEWAY_YAML, env={})
    return Router(cfg.routes, {p.name for p in cfg.pools}, random.Random(42))


def match(path, method="GET", **headers):
    return router().match(method, path, CIMultiDict(headers))


def test_default_route():
    m = match("/users/7")
    assert (m.route, m.pool, m.path) == ("default", "all", "/users/7")
    assert match("/health").pool == "all"


def test_unknown_path_has_no_route():
    assert match("/nope") is None
    assert match("/usersX") is None


def test_path_routing_strips_prefix():
    m = match("/rust/users/1")
    assert (m.route, m.pool, m.path) == ("rust", "api-rust", "/users/1")
    assert match("/go").path == "/"


def test_header_routing_wins_and_ignores_unknown_pools():
    m = match("/users", **{"X-Backend": "api-go"})
    assert (m.route, m.pool) == ("by-header", "api-go")
    assert match("/users", **{"X-Backend": "nope"}).route == "default"


def test_canary_split_follows_weights():
    r = router()
    counts = Counter(r.match("GET", "/canary/users", CIMultiDict()).pool for _ in range(2000))
    assert 0.85 < counts["compiled"] / 2000 < 0.95
    assert r.match("GET", "/canary/users", CIMultiDict()).path == "/users"


def test_methods_and_exact_headers():
    routes = [RouteConfig("writes", path_prefixes=["/users"], methods=["POST"], headers={"X-Tenant": "a"},
                          pools=[WeightedPool("p", 1)])]
    r = Router(routes, {"p"})
    assert r.match("POST", "/users", CIMultiDict({"x-tenant": "a"})).pool == "p"
    assert r.match("GET", "/users", CIMultiDict({"X-Tenant": "a"})) is None
    assert r.match("POST", "/users", CIMultiDict({"X-Tenant": "b"})) is None
