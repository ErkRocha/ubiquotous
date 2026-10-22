from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

Nome = Annotated[str, Field(min_lenght=1)]
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Cpf = Annotated[str, Field(pattern=r"^[0-9]{11}$")]

class NovoUsuario(BaseModel):
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
