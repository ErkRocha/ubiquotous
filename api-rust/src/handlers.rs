use axum::{
    body::Bytes,
    extract::{Path, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use deadpool_postgres::Pool;

use crate::{
    errors::ApiError,
    models::{self, Usuario},
    validacao::{ler_corpo, validar_id, validar_usuario},
};

type Resultado = Result<Response, ApiError>;

fn ou_404(usuario: Option<Usuario>) -> Resultado {
    let usuario = usuario.ok_or_else(ApiError::nao_encontrado)?;
    Ok(Json(usuario).into_response())
}

pub async fn criar(State(pool): State<Pool>, headers: HeaderMap, body: Bytes) -> Resultado {
    let dados = validar_usuario(&ler_corpo(&headers, &body)?, false)?;
    let usuario = models::criar(&pool, &dados).await?;
    let location = format!("/users/{}", usuario.id);
    Ok((StatusCode::CREATED, [(header::LOCATION, location)], Json(usuario)).into_response())
}

pub async fn listar(State(pool): State<Pool>) -> Resultado {
    Ok(Json(models::listar(&pool).await?).into_response())
}

pub async fn buscar(State(pool): State<Pool>, Path(id): Path<String>) -> Resultado {
    let id = validar_id(&id)?;
    ou_404(models::buscar_por_id(&pool, id).await?)
}

pub async fn substituir(
    State(pool): State<Pool>,
    Path(id): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Resultado {
    let id = validar_id(&id)?;
    let dados = validar_usuario(&ler_corpo(&headers, &body)?, false)?;
    ou_404(models::atualizar(&pool, id, &dados).await?)
}

pub async fn atualizar_parcial(
    State(pool): State<Pool>,
    Path(id): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Resultado {
    let id = validar_id(&id)?;
    let dados = validar_usuario(&ler_corpo(&headers, &body)?, true)?;
    ou_404(models::atualizar_parcial(&pool, id, &dados).await?)
}

pub async fn remover(State(pool): State<Pool>, Path(id): Path<String>) -> Resultado {
    let id = validar_id(&id)?;
    if !models::remover(&pool, id).await? {
        return Err(ApiError::nao_encontrado());
    }
    Ok(StatusCode::NO_CONTENT.into_response())
}
