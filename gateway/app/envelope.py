"""Erros gerados pelo próprio gateway.

Usam o mesmo formato de erro das APIs ({"error": {"code": ..., "message": ...}})
para que o cliente não precise saber se o erro veio do gateway ou de um upstream.
Respostas de sucesso não têm envelope: o corpo do upstream é repassado como veio.
"""

from aiohttp import web


def error(status: int, code: str, message: str, headers: dict | None = None) -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status, headers=headers)
