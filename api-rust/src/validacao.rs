use std::sync::LazyLock;

use axum::http::{header, HeaderMap};
use chrono::{Datelike, NaiveDate};
use regex::Regex;
use serde_json::{Map, Value};

use crate::errors::ApiError;

// Mesmas regras do schemas.py da API Python (o \s do Rust já é Unicode, igual ao do Python).
static EMAIL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[^@\s]+@[^@\s]+\.[^@\s]+$").unwrap());
static CPF: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[0-9]{11}$").unwrap());
static DATA: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$").unwrap());
static ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^-?[0-9]+$").unwrap());

/// Campos validados. None = não enviado (só acontece no PATCH).
#[derive(Default)]
pub struct DadosUsuario {
    pub name: Option<String>,
    pub email: Option<String>,
    pub birthday: Option<NaiveDate>,
    pub cpf: Option<String>,
}

/// O corpo precisa ser um objeto JSON.
pub fn ler_corpo(headers: &HeaderMap, body: &[u8]) -> Result<Map<String, Value>, ApiError> {
    if let Some(ct) = headers.get(header::CONTENT_TYPE) {
        let tipo = ct.to_str().unwrap_or("").split(';').next().unwrap_or("").trim().to_ascii_lowercase();
        let json = tipo == "application/json"
            || (tipo.starts_with("application/") && tipo.ends_with("+json"));
        if !json {
            return Err(ApiError::corpo_invalido());
        }
    }
    if body.is_empty() {
        return Err(ApiError::corpo_invalido());
    }
    match serde_json::from_slice(body) {
        Ok(Value::Object(corpo)) => Ok(corpo),
        _ => Err(ApiError::corpo_invalido()),
    }
}

fn texto(valor: &Value, valido: impl Fn(&str) -> bool) -> Option<String> {
    valor.as_str().filter(|s| valido(s)).map(String::from)
}

fn data(valor: &Value) -> Option<NaiveDate> {
    let s = valor.as_str().filter(|s| DATA.is_match(s))?;
    NaiveDate::parse_from_str(s, "%Y-%m-%d").ok().filter(|d| d.year() >= 1)
}

/// parcial = false (POST/PUT): todos os campos obrigatórios.
/// parcial = true (PATCH): campo ausente ou null é ignorado.
pub fn validar_usuario(corpo: &Map<String, Value>, parcial: bool) -> Result<DadosUsuario, ApiError> {
    let mut d = DadosUsuario::default();

    for campo in ["name", "email", "birthday", "cpf"] {
        let valor = match corpo.get(campo) {
            None | Some(Value::Null) if parcial => continue,
            None | Some(Value::Null) => return Err(ApiError::campo_invalido(campo)),
            Some(v) => v,
        };
        let ok = match campo {
            "name" => {
                d.name = texto(valor, |s| !s.is_empty());
                d.name.is_some()
            }
            "email" => {
                d.email = texto(valor, |s| EMAIL.is_match(s));
                d.email.is_some()
            }
            "birthday" => {
                d.birthday = data(valor);
                d.birthday.is_some()
            }
            _ => {
                d.cpf = texto(valor, |s| CPF.is_match(s));
                d.cpf.is_some()
            }
        };
        if !ok {
            return Err(ApiError::campo_invalido(campo));
        }
    }
    Ok(d)
}

/// Devolve o id. Se ele não cabe na coluna SERIAL, o usuário não existe (404).
pub fn validar_id(valor: &str) -> Result<i32, ApiError> {
    if !ID.is_match(valor) {
        return Err(ApiError::campo_invalido("id"));
    }
    valor.parse::<i32>().map_err(|_| ApiError::nao_encontrado())
}
