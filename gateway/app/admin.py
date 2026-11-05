"""Endpoints do próprio gateway, em /_gateway/ (não são repassados aos upstreams).

GET  /_gateway/health       o gateway está no ar
GET  /_gateway/status       estado completo (upstreams, pools, rotas, cache...)
POST /_gateway/cache/flush  esvazia o cache
"""

import time

from aiohttp import web

from .gateway import Gateway


def _ok(data, status=200):
    # Sem envelope: o JSON da resposta é o próprio objeto, como nas APIs.
    return web.json_response(data, status=status)


def routes(gw: Gateway) -> list[web.RouteDef]:
    async def health(_):
        return _ok({"status": "ok"})

    async def status(_):
        cfg = gw.config
        return _ok({
            "uptime_seconds": int(time.time() - gw.started_at),
            "total_requests": gw.total_requests,
            "upstreams": [
                {
                    "name": u.name,
                    "url": u.url,
                    "healthy": u.healthy,
                    "available": u.available(),
                    "circuit": {
                        "state": u.breaker.state,
                        "failures": u.breaker.failures,
                        "failure_threshold": u.breaker.failure_threshold,
                        "retry_in_seconds": round(u.breaker.retry_in(), 1),
                    },
                    "active_connections": u.active_connections,
                    "latency_ewma_ms": None if u.latency_ewma_ms is None else round(u.latency_ewma_ms, 1),
                    "requests": u.requests,
                    "errors": u.errors,
                    "simulate_latency_ms": u.simulate_latency_ms,
                }
                for u in gw.upstreams.values()
            ],
            "pools": [
                {"name": p.name, "strategy": p.strategy, "upstreams": [u.name for u in p.upstreams]}
                for p in gw.pools.values()
            ],
            "routes": [
                {
                    "name": r.name,
                    "path_prefixes": r.path_prefixes,
                    "methods": r.methods,
                    "headers": r.headers,
                    "headers_present": r.headers_present,
                    "pool_from_header": r.pool_from_header,
                    "pools": [{"pool": p.pool, "weight": p.weight} for p in r.pools],
                    "strip_prefix": r.strip_prefix,
                }
                for r in cfg.routes
            ],
            "rate_limit": {
                "enabled": cfg.rate_limit_enabled,
                "capacity": cfg.rate_limit_capacity,
                "refill_per_second": cfg.rate_limit_refill,
                "clients": len(gw.limiter.buckets),
                "rejected": gw.limiter.rejected,
            },
            "cache": {
                "enabled": cfg.cache_enabled,
                "ttl_seconds": cfg.cache_ttl,
                "entries": len(gw.cache.entries),
                "hits": gw.cache.hits,
                "misses": gw.cache.misses,
                "bypasses": gw.cache.bypasses,
            },
            "circuit_breaker": {"failure_threshold": cfg.cb_failure_threshold, "open_seconds": cfg.cb_open_seconds},
            "health_check": {"enabled": cfg.health_enabled, "path": cfg.health_path,
                             "interval_seconds": cfg.health_interval},
            "recent": list(gw.recent),
        })

    async def flush_cache(_):
        removed = len(gw.cache.entries)
        gw.cache.clear()
        return _ok({"removed": removed})

    return [
        web.get("/_gateway/health", health),
        web.get("/_gateway/status", status),
        web.post("/_gateway/cache/flush", flush_cache),
    ]
