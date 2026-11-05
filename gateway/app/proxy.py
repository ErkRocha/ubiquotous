"""Reverse proxy: repassa a requisição para o upstream e traz a resposta.

O cliente só conhece o gateway; os upstreams ficam escondidos atrás dele.
No caminho, o proxy:

- remove os headers "hop-by-hop" (Connection, Keep-Alive, Transfer-Encoding...):
  eles valem só para UMA conexão TCP (cliente<->gateway), não para a próxima
  (gateway<->upstream);
- acrescenta X-Forwarded-For / X-Forwarded-Proto / X-Forwarded-Host, para o
  upstream saber quem é o cliente original;
- repassa o X-Request-Id, que liga o log do gateway ao log do upstream.
"""

import asyncio
from dataclasses import dataclass

import aiohttp
from multidict import CIMultiDict

from .upstream import Upstream

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "trailers", "transfer-encoding", "upgrade",
}
# Recalculados pelo aiohttp para a nova requisição/resposta.
RECOMPUTED = {"host", "content-length"}


class UpstreamUnavailable(Exception):
    """Não deu para conectar ou a conexão caiu (vira 502)."""


class UpstreamTimeout(Exception):
    """O upstream demorou mais que o timeout (vira 504)."""


@dataclass
class ProxyResponse:
    status: int
    headers: CIMultiDict
    body: bytes


def forwardable(headers) -> CIMultiDict:
    connection_tokens = {t.strip().lower() for t in headers.get("Connection", "").split(",") if t.strip()}
    skip = HOP_BY_HOP | RECOMPUTED | connection_tokens
    return CIMultiDict((k, v) for k, v in headers.items() if k.lower() not in skip)


async def forward(
    session: aiohttp.ClientSession,
    upstream: Upstream,
    method: str,
    path: str,
    query: str,
    headers,
    body: bytes,
    *,
    remote_addr: str,
    host: str,
    scheme: str,
    request_id: str,
    timeout: float,
) -> ProxyResponse:
    out = forwardable(headers)
    previous = headers.get("X-Forwarded-For")
    # Cada proxy no caminho acrescenta o endereço de quem falou com ele.
    out["X-Forwarded-For"] = f"{previous}, {remote_addr}" if previous else remote_addr
    out["X-Forwarded-Proto"] = scheme
    out["X-Forwarded-Host"] = host
    out["X-Request-Id"] = request_id

    url = upstream.url + path + (f"?{query}" if query else "")
    try:
        if upstream.simulate_latency_ms:
            await asyncio.sleep(upstream.simulate_latency_ms / 1000)  # só para a aula
        async with session.request(
            method, url, headers=out, data=body or None,
            timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False,
        ) as resp:
            payload = await resp.read()
            return ProxyResponse(resp.status, forwardable(resp.headers), payload)
    except asyncio.TimeoutError as exc:
        raise UpstreamTimeout(str(exc)) from exc
    except aiohttp.ClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
