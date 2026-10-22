mod errors;
mod handlers;
mod models;
mod validacao;

use std::str::FromStr;

use axum::{routing::get, Router};
use deadpool_postgres::{Manager, Pool};
use tokio_postgres::NoTls;

#[tokio::main]
async fn main() {
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgresql://postgres:postgres@localhost:5432/users_db".into());
    let port = std::env::var("PORT").unwrap_or_else(|_| "8000".into());

    let config = tokio_postgres::Config::from_str(&database_url).expect("DATABASE_URL inválida");
    let pool = Pool::builder(Manager::new(config, NoTls))
        .max_size(16)
        .build()
        .expect("erro ao criar o pool");

    // falha logo na subida se o banco não estiver acessível
    drop(pool.get().await.expect("não foi possível conectar no banco"));

    let app = Router::new()
        .route("/users", get(handlers::listar).post(handlers::criar))
        .route(
            "/users/{id}",
            get(handlers::buscar)
                .put(handlers::substituir)
                .patch(handlers::atualizar_parcial)
                .delete(handlers::remover),
        )
        .with_state(pool);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}"))
        .await
        .expect("não foi possível abrir a porta");
    println!("API Rust ouvindo na porta {port}");
    axum::serve(listener, app).await.unwrap();
}
