"""Leitura do gateway.yaml.

O arquivo aceita ${VAR:-default}: a substituição é feita no TEXTO, antes do
parse do YAML, então `capacity: ${RATE_LIMIT_BURST:-200}` vira o número 200.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENV_VAR = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


def expand_env(text: str, env=os.environ) -> str:
    # Igual ao shell: o default vale quando a variável não existe OU está vazia.
    return ENV_VAR.sub(lambda m: env.get(m.group(1)) or m.group(2) or "", text)


def as_bool(value) -> bool:
    # Os valores vêm entre aspas no YAML, então bool("false") daria True.
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class UpstreamConfig:
    name: str
    url: str
    simulate_latency_ms: int = 0


@dataclass
class PoolConfig:
    name: str
    upstreams: list[str]
    strategy: str = "round_robin"


@dataclass
class WeightedPool:
    pool: str
    weight: int


@dataclass
class RouteConfig:
    name: str
    path_prefixes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    headers_present: list[str] = field(default_factory=list)
    pools: list[WeightedPool] = field(default_factory=list)
    pool_from_header: str | None = None
    strip_prefix: bool = False


@dataclass
class Config:
    port: int
    trust_forwarded_for: bool
    upstreams: list[UpstreamConfig]
    pools: list[PoolConfig]
    routes: list[RouteConfig]
    proxy_timeout: float = 5
    proxy_retries: int = 1
    cb_failure_threshold: int = 3
    cb_open_seconds: float = 10
    health_enabled: bool = True
    health_path: str = "/health"
    health_interval: float = 5
    health_timeout: float = 2
    health_unhealthy_threshold: int = 2
    health_healthy_threshold: int = 1
    rate_limit_enabled: bool = True
    rate_limit_capacity: int = 200
    rate_limit_refill: float = 100
    cache_enabled: bool = True
    cache_ttl: float = 5
    cache_max_entries: int = 1000


def _route(raw: dict) -> RouteConfig:
    prefixes = raw.get("path_prefix", [])
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    if "pool" in raw:
        pools = [WeightedPool(raw["pool"], 1)]
    else:
        pools = [WeightedPool(p["pool"], int(p.get("weight", 1))) for p in raw.get("pools", [])]
    return RouteConfig(
        name=raw["name"],
        path_prefixes=[p.rstrip("/") or "/" for p in prefixes],
        methods=[m.upper() for m in raw.get("methods", [])],
        headers={k: str(v) for k, v in raw.get("headers", {}).items()},
        headers_present=raw.get("headers_present", []),
        pools=pools,
        pool_from_header=raw.get("pool_from_header"),
        strip_prefix=as_bool(raw.get("strip_prefix", False)),
    )


def parse(text: str, env=os.environ) -> Config:
    raw = yaml.safe_load(expand_env(text, env))
    server = raw.get("server", {})
    proxy = raw.get("proxy", {})
    cb = raw.get("circuit_breaker", {})
    hc = raw.get("health_check", {})
    rl = raw.get("rate_limit", {})
    cache = raw.get("cache", {})
    return Config(
        port=int(server.get("port", 8080)),
        trust_forwarded_for=as_bool(server.get("trust_forwarded_for", False)),
        upstreams=[
            UpstreamConfig(u["name"], u["url"].rstrip("/"), int(u.get("simulate_latency_ms") or 0))
            for u in raw["upstreams"]
        ],
        pools=[
            PoolConfig(name, p["upstreams"], p.get("strategy") or "round_robin")
            for name, p in raw["pools"].items()
        ],
        routes=[_route(r) for r in raw["routes"]],
        proxy_timeout=float(proxy.get("timeout_seconds", 5)),
        proxy_retries=int(proxy.get("retries", 1)),
        cb_failure_threshold=int(cb.get("failure_threshold", 3)),
        cb_open_seconds=float(cb.get("open_seconds", 10)),
        health_enabled=as_bool(hc.get("enabled", True)),
        health_path=hc.get("path", "/health"),
        health_interval=float(hc.get("interval_seconds", 5)),
        health_timeout=float(hc.get("timeout_seconds", 2)),
        health_unhealthy_threshold=int(hc.get("unhealthy_threshold", 2)),
        health_healthy_threshold=int(hc.get("healthy_threshold", 1)),
        rate_limit_enabled=as_bool(rl.get("enabled", True)),
        rate_limit_capacity=int(rl.get("capacity", 200)),
        rate_limit_refill=float(rl.get("refill_per_second", 100)),
        cache_enabled=as_bool(cache.get("enabled", True)),
        cache_ttl=float(cache.get("ttl_seconds", 5)),
        cache_max_entries=int(cache.get("max_entries", 1000)),
    )


def load(path: str | None = None) -> Config:
    path = path or os.environ.get("GATEWAY_CONFIG") or Path(__file__).parent.parent / "gateway.yaml"
    return parse(Path(path).read_text())
