"""O caminho de uma requisição pelo gateway, passo a passo.

    cliente
      │
      ├─ 1. rate limit ............ cliente passou do limite? -> 429
      ├─ 2. traffic routing ....... qual pool atende este path/header? nenhum -> 404
      ├─ 3. cache ................. GET já está no cache? -> responde sem ir ao upstream
      ├─ 4. load balancing ........ escolhe um upstream do pool (saudável + circuito fechado)
      ├─ 5. reverse proxy ......... repassa e espera a resposta (falhou? tenta outro: retry)
      ├─ 6. circuit breaker ....... anota sucesso/falha do upstream
      └─ 7. cache ................. guarda o GET 200 / invalida em escrita
      │
    resposta (+ headers X-Upstream, X-Cache, X-Request-Id, X-RateLimit-*)
"""

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass

import aiohttp
from aiohttp import web
from multidict import CIMultiDict

from . import proxy
from .balancers import Balancer, PickContext, make_balancer
from .cache import ResponseCache
from .circuit_breaker import CircuitBreaker
from .config import Config
from .envelope import error
from .rate_limit import TokenBucketLimiter
from .routing import Router
from .upstream import Upstream

log = logging.getLogger("gateway")

IDEMPOTENT = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Pool:
    name: str
    strategy: str
    upstreams: list[Upstream]
    balancer: Balancer


class Gateway:
    """Todo o estado do gateway (fica na memória do processo)."""

    def __init__(self, config: Config, clock=time.monotonic):
        self.config = config
        self.upstreams = {
            u.name: Upstream(u.name, u.url,
                             CircuitBreaker(u.name, config.cb_failure_threshold, config.cb_open_seconds, clock),
                             u.simulate_latency_ms)
            for u in config.upstreams
        }
        self.pools = {
            p.name: Pool(p.name, p.strategy, [self.upstreams[n] for n in p.upstreams], make_balancer(p.strategy, p.name))
            for p in config.pools
        }
        self.router = Router(config.routes, set(self.pools))
        self.limiter = TokenBucketLimiter(config.rate_limit_capacity, config.rate_limit_refill, clock)
        self.cache = ResponseCache(config.cache_ttl, config.cache_max_entries, clock)
        self.session: aiohttp.ClientSession | None = None  # criada no startup (main.py)
        self.recent: deque[dict] = deque(maxlen=50)
        self.total_requests = 0
        self.started_at = time.time()

    # ------------------------------------------------------------------ pipeline

    async def handle(self, request: web.Request) -> web.Response:
        started = time.monotonic()
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        client_ip = self.client_ip(request)
        path = request.rel_url.raw_path
        query = request.rel_url.raw_query_string
        info = {"route": None, "pool": None, "upstream": None, "cache": None}

        response = await self._pipeline(request, client_ip, request_id, path, query, info)

        response.headers["X-Request-Id"] = request_id
        ms = (time.monotonic() - started) * 1000
        self._record(request, path, client_ip, request_id, response.status, ms, info)
        return response

    async def _pipeline(self, request, client_ip, request_id, path, query, info) -> web.Response:
        method = request.method

        # 1. Rate limit -------------------------------------------------------
        limit_headers = {}
        if self.config.rate_limit_enabled:
            decision = self.limiter.check(client_ip)
            limit_headers = {"X-RateLimit-Limit": str(decision.limit),
                             "X-RateLimit-Remaining": str(decision.remaining)}
            if not decision.allowed:
                return error(429, "RATE_LIMITED", "Limite de requisições excedido.",
                             {**limit_headers, "Retry-After": str(decision.retry_after)})

        # 2. Traffic routing --------------------------------------------------
        match = self.router.match(method, path, request.headers)
        if match is None:
            return error(404, "NOT_FOUND", "Rota não encontrada.", limit_headers)
        pool = self.pools[match.pool]
        info.update(route=match.route, pool=pool.name)
        gateway_headers = {**limit_headers, "X-Gateway-Route": match.route, "X-Gateway-Pool": pool.name,
                           "X-Gateway-Strategy": pool.strategy}

        # 3. Cache (leitura) --------------------------------------------------
        cache_key = None
        if self.config.cache_enabled and method == "GET":
            if "no-cache" in request.headers.get("Cache-Control", ""):
                info["cache"] = "BYPASS"
                self.cache.bypasses += 1
            else:
                cache_key = ResponseCache.key(pool.name, match.path, query)
                hit = self.cache.get(cache_key)
                if hit:
                    self.cache.hits += 1
                    info.update(cache="HIT", upstream=hit.headers.get("X-Upstream"))
                    return web.Response(status=hit.status, body=hit.body, headers={
                        **hit.headers, **gateway_headers, "X-Cache": "HIT", "Age": str(self.cache.age(hit))})
                info["cache"] = "MISS"
                self.cache.misses += 1

        body = await request.read()
        ctx = PickContext(client_ip=client_ip, cookies=dict(request.cookies), pool=pool.upstreams)

        # 4 + 5 + 6. Load balancing, proxy e circuit breaker, com retry ----------
        attempts = 1 + (self.config.proxy_retries if method in IDEMPOTENT else 0)
        tried: list[Upstream] = []
        failure = None
        for _ in range(attempts):
            candidates = [u for u in pool.upstreams if u.available() and u not in tried]
            if not candidates:
                break
            upstream = pool.balancer.pick(candidates, ctx)
            tried.append(upstream)
            info["upstream"] = upstream.name
            try:
                result = await self._call(upstream, request, match.path, query, body, request_id)
            except proxy.UpstreamTimeout:
                failure = (504, "GATEWAY_TIMEOUT", "O upstream demorou demais para responder.")
                log.warning("%s %s: %s deu timeout, tentando outro", method, path, upstream.name)
                continue
            except proxy.UpstreamUnavailable:
                failure = (502, "BAD_GATEWAY", "Nenhum upstream respondeu.")
                log.warning("%s %s: %s não respondeu, tentando outro", method, path, upstream.name)
                continue

            # 7. Cache (escrita / invalidação) ---------------------------------
            headers = {k: v for k, v in result.headers.items() if k.lower() != "set-cookie"}
            headers["X-Upstream"] = upstream.name
            if cache_key and result.status == 200:
                self.cache.put(cache_key, match.path, result.status, headers, result.body)
            if method in WRITES and result.status < 400:
                self.cache.invalidate(match.path)

            out = CIMultiDict(result.headers)
            out.update({**gateway_headers, "X-Upstream": upstream.name})
            if info["cache"]:
                out["X-Cache"] = info["cache"]
            response = web.Response(status=result.status, body=result.body, headers=out)
            for name, value in pool.balancer.response_cookies(upstream, ctx).items():
                response.set_cookie(name, value, path="/", httponly=True, samesite="Lax")
            return response

        if failure is None:
            return error(503, "NO_UPSTREAM_AVAILABLE", "Nenhum upstream disponível.", gateway_headers)
        return error(failure[0], failure[1], failure[2], gateway_headers)

    async def _call(self, upstream, request, path, query, body, request_id) -> proxy.ProxyResponse:
        upstream.breaker.before_request()
        upstream.active_connections += 1
        upstream.requests += 1
        started = time.monotonic()
        try:
            result = await proxy.forward(
                self.session, upstream, request.method, path, query, request.headers, body,
                remote_addr=request.remote or "", host=request.host, scheme=request.scheme,
                request_id=request_id, timeout=self.config.proxy_timeout,
            )
        except (proxy.UpstreamTimeout, proxy.UpstreamUnavailable):
            upstream.errors += 1
            upstream.breaker.record_failure()
            raise
        finally:
            upstream.active_connections -= 1

        upstream.record_latency((time.monotonic() - started) * 1000)
        if result.status >= 500:
            upstream.errors += 1
            upstream.breaker.record_failure()
        else:
            upstream.breaker.record_success()
        return result

    # ------------------------------------------------------------------ apoio

    def client_ip(self, request: web.Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if self.config.trust_forwarded_for and forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote or ""

    def _record(self, request, path, client_ip, request_id, status, ms, info) -> None:
        self.total_requests += 1
        entry = {"time": time.time(), "id": request_id, "method": request.method, "path": path,
                 "client": client_ip, "status": status, "ms": round(ms, 1), **info}
        self.recent.appendleft(entry)
        if status == 429 and info["route"] is None:
            log.warning("%s %s -> BLOQUEADA pelo rate limit (429) client=%s id=%s",
                        request.method, path, client_ip, request_id)
            return
        target = f"CACHE HIT (de {info['upstream']})" if info["cache"] == "HIT" else info["upstream"] or "-"
        log.info("%s %s -> %s %d %.1fms route=%s cache=%s client=%s id=%s",
                 request.method, path, target, status, ms,
                 info["route"] or "-", info["cache"] or "-", client_ip, request_id)
