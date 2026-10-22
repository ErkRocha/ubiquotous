use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use tokio_postgres::error::SqlState;

pub struct ApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl ApiError {
    fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self { status, code, message: message.into() }
    }

    pub fn nao_encontrado() -> Self {
        Self::new(StatusCode::NOT_FOUND, "NOT_FOUND", "Usuário não encontrado.")
    }

    pub fn campo_invalido(campo: &str) -> Self {
        Self::new(
            StatusCode::BAD_REQUEST,
            "VALIDATION_ERROR",
            format!("O campo '{campo}' é inválido ou está ausente."),
        )
    }

    pub fn corpo_invalido() -> Self {
        Self::new(
            StatusCode::BAD_REQUEST,
            "VALIDATION_ERROR",
            "Corpo da requisição ausente ou com JSON inválido.",
        )
    }

    fn interno(err: impl std::fmt::Display) -> Self {
        eprintln!("Erro não tratado: {err}");
        Self::new(StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Erro interno do servidor.")
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let corpo = json!({ "error": { "code": self.code, "message": self.message } });
        (self.status, Json(corpo)).into_response()
    }
}

// Erro do banco: UNIQUE vira 409 (nome da constraint no db/init.sql), o resto vira 500.
impl From<tokio_postgres::Error> for ApiError {
    fn from(err: tokio_postgres::Error) -> Self {
        match err.as_db_error() {
            Some(db) if *db.code() == SqlState::UNIQUE_VIOLATION => match db.constraint() {
                Some("users_email_key") => {
                    Self::new(StatusCode::CONFLICT, "EMAIL_IN_USE", "Este e-mail já está cadastrado.")
                }
                Some("users_cpf_key") => {
                    Self::new(StatusCode::CONFLICT, "CPF_IN_USE", "Este CPF já está cadastrado.")
                }
                _ => Self::new(StatusCode::CONFLICT, "CONFLICT", "Registro duplicado."),
            },
            _ => Self::interno(err),
        }
    }
}

// Falha ao pegar conexão do pool.
impl From<deadpool_postgres::PoolError> for ApiError {
    fn from(err: deadpool_postgres::PoolError) -> Self {
        Self::interno(err)
    }
}
