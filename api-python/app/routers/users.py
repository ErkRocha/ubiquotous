from fastapi import APIRouter, Response

from app import models
from app.errors import ApiError
from app.schemas import AtualizarUsuario, NovoUsuario, Usuario

router = APIRouter(prefix="/users", tags=["Users"])


def nao_encontrado() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Usuário não encontrado.")


@router.post("", response_model=Usuario, status_code=201)
def criar(dados: NovoUsuario, response: Response):
    usuario = models.criar(dados.name, dados.email, dados.birthday, dados.cpf)
    response.headers["Location"] = f"/users/{usuario['id']}"
    return usuario


@router.get("", response_model=list[Usuario])
def listar():
    return models.listar()


@router.get("/{id}", response_model=Usuario)
def buscar(id: int):
    usuario = models.buscar_por_id(id)
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.put("/{id}", response_model=Usuario)
def substituir(id: int, dados: NovoUsuario):
    usuario = models.atualizar(id, dados.name, dados.email, dados.birthday, dados.cpf)
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.patch("/{id}", response_model=Usuario)
def atualizar_parcial(id: int, dados: AtualizarUsuario):
    usuario = models.atualizar_parcial(
        id, dados.name, dados.email, dados.birthday, dados.cpf
    )
    if usuario is None:
        raise nao_encontrado()
    return usuario


@router.delete("/{id}", status_code=204, response_class=Response)
def remover(id: int):
    if not models.remover(id):
        raise nao_encontrado()
    return Response(status_code=204)  # 204 sem corpo e sem Content-Type
