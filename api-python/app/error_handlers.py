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
