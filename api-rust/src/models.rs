use deadpool_postgres::Pool;
use serde::Serialize;
use tokio_postgres::Row;

use crate::{errors::ApiError, validacao::DadosUsuario};

// Mesmo SQL da API Python: o Postgres formata as datas,
// então as 4 APIs devolvem exatamente o mesmo formato.
const COLUNAS: &str = r#"
    id,
    name,
    email,
    to_char(birthday, 'YYYY-MM-DD') AS birthday,
    cpf,
    to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS inserted_at,
    to_char(updated_at  AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at
"#;

// A ordem dos campos aqui é a ordem no JSON de resposta.
#[derive(Serialize)]
pub struct Usuario {
    pub id: i32,
    pub name: String,
    pub email: String,
    pub birthday: String,
    pub cpf: String,
    pub inserted_at: String,
    pub updated_at: String,
}

impl From<Row> for Usuario {
    fn from(row: Row) -> Self {
        Self {
            id: row.get("id"),
            name: row.get("name"),
            email: row.get("email"),
            birthday: row.get("birthday"),
            cpf: row.get("cpf"),
            inserted_at: row.get("inserted_at"),
            updated_at: row.get("updated_at"),
        }
    }
}

pub async fn criar(pool: &Pool, d: &DadosUsuario) -> Result<Usuario, ApiError> {
    let conn = pool.get().await?;
    let sql = format!(
        "INSERT INTO users (name, email, birthday, cpf)
         VALUES ($1, $2, $3, $4)
         RETURNING {COLUNAS}"
    );
    let row = conn.query_one(&sql, &[&d.name, &d.email, &d.birthday, &d.cpf]).await?;
    Ok(row.into())
}

pub async fn listar(pool: &Pool) -> Result<Vec<Usuario>, ApiError> {
    let conn = pool.get().await?;
    let sql = format!("SELECT {COLUNAS} FROM users ORDER BY id");
    let rows = conn.query(&sql, &[]).await?;
    Ok(rows.into_iter().map(Usuario::from).collect())
}

pub async fn buscar_por_id(pool: &Pool, id: i32) -> Result<Option<Usuario>, ApiError> {
    let conn = pool.get().await?;
    let sql = format!("SELECT {COLUNAS} FROM users WHERE id = $1");
    Ok(conn.query_opt(&sql, &[&id]).await?.map(Usuario::from))
}

pub async fn atualizar(pool: &Pool, id: i32, d: &DadosUsuario) -> Result<Option<Usuario>, ApiError> {
    let conn = pool.get().await?;
    let sql = format!(
        "UPDATE users
         SET name = $1, email = $2, birthday = $3, cpf = $4
         WHERE id = $5
         RETURNING {COLUNAS}"
    );
    let row = conn.query_opt(&sql, &[&d.name, &d.email, &d.birthday, &d.cpf, &id]).await?;
    Ok(row.map(Usuario::from))
}

pub async fn atualizar_parcial(
    pool: &Pool,
    id: i32,
    d: &DadosUsuario,
) -> Result<Option<Usuario>, ApiError> {
    let conn = pool.get().await?;
    let sql = format!(
        "UPDATE users
         SET name     = COALESCE($1, name),
             email    = COALESCE($2, email),
             birthday = COALESCE($3, birthday),
             cpf      = COALESCE($4, cpf)
         WHERE id = $5
         RETURNING {COLUNAS}"
    );
    let row = conn.query_opt(&sql, &[&d.name, &d.email, &d.birthday, &d.cpf, &id]).await?;
    Ok(row.map(Usuario::from))
}

pub async fn remover(pool: &Pool, id: i32) -> Result<bool, ApiError> {
    let conn = pool.get().await?;
    Ok(conn.execute("DELETE FROM users WHERE id = $1", &[&id]).await? > 0)
}
