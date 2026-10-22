export class ApiError extends Error {
  constructor(statusCode, code, message) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
  }
}

export const naoEncontrado = () => new ApiError(404, "NOT_FOUND", "Usuário não encontrado.");

export const campoInvalido = (campo) =>
  new ApiError(400, "VALIDATION_ERROR", `O campo '${campo}' é inválido ou está ausente.`);

export const corpoInvalido = () =>
  new ApiError(400, "VALIDATION_ERROR", "Corpo da requisição ausente ou com JSON inválido.");
