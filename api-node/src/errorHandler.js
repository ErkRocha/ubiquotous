import { ApiError } from "./errors.js";

// nome da constraint no banco (db/init.sql) -> erro devolvido pela API
const CONFLITOS = {
  users_email_key: ["EMAIL_IN_USE", "Este e-mail já está cadastrado."],
  users_cpf_key: ["CPF_IN_USE", "Este CPF já está cadastrado."],
};

const erro = (res, status, code, message) =>
  res.status(status).json({ error: { code, message } });

// eslint-disable-next-line no-unused-vars
export function errorHandler(err, req, res, next) {
  if (err instanceof ApiError) {
    return erro(res, err.statusCode, err.code, err.message);
  }
  if (err.code === "23505") {
    const [code, message] = CONFLITOS[err.constraint] ?? ["CONFLICT", "Registro duplicado."];
    return erro(res, 409, code, message);
  }
  console.error("Erro não tratado", err);
  return erro(res, 500, "INTERNAL_ERROR", "Erro interno do servidor.");
}
