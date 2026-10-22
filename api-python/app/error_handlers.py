import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation

from app.errors import ApiError

logger = logging.getLogger("uvicorn.error")

CONFLITOS = {
    "users_email_key": ("EMAIL_IN_USE", "Este e-mail já está cadastrado."),
    "users_cpf_key": ("CPF_IN_USE", "Este CPF já está cadastrado.")
},

