import { campoInvalido, corpoInvalido } from "./errors.js";

// Mesmas regras do schemas.py da API Python.
// [\t-\r\u0085\p{Z}] é o "\s" Unicode do Python/Rust (o \s do JS também pega o U+FEFF).
const EMAIL = /^[^@\t-\r\u0085\p{Z}]+@[^@\t-\r\u0085\p{Z}]+\.[^@\t-\r\u0085\p{Z}]+$/u;
const CPF = /^[0-9]{11}$/;
const DATA = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;

function dataValida(valor) {
  const m = DATA.exec(valor);
  if (!m) return false;
  const [ano, mes, dia] = m.slice(1).map(Number);
  if (ano < 1 || mes < 1 || mes > 12 || dia < 1) return false;
  const bissexto = (ano % 4 === 0 && ano % 100 !== 0) || ano % 400 === 0;
  const diasNoMes = [31, bissexto ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return dia <= diasNoMes[mes - 1];
}

const REGRAS = {
  name: (v) => typeof v === "string" && v.length >= 1,
  email: (v) => typeof v === "string" && EMAIL.test(v),
  birthday: (v) => typeof v === "string" && dataValida(v),
  cpf: (v) => typeof v === "string" && CPF.test(v),
};

// O corpo chega como texto (ver server.js). Precisa ser um objeto JSON.
export function lerCorpo(req) {
  const contentType = req.headers["content-type"];
  if (contentType && !/^application\/([^;]*\+)?json\b/i.test(contentType)) {
    throw corpoInvalido();
  }
  if (typeof req.body !== "string" || req.body.length === 0) throw corpoInvalido();

  let corpo;
  try {
    corpo = JSON.parse(req.body);
  } catch {
    throw corpoInvalido();
  }
  if (corpo === null || typeof corpo !== "object" || Array.isArray(corpo)) {
    throw corpoInvalido();
  }
  return corpo;
}

// parcial = false (POST/PUT): todos os campos obrigatórios.
// parcial = true (PATCH): campo ausente ou null é ignorado.
export function validarUsuario(corpo, parcial) {
  const dados = {};
  for (const [campo, valido] of Object.entries(REGRAS)) {
    const valor = corpo[campo];
    if (valor === undefined || valor === null) {
      if (parcial) continue;
      throw campoInvalido(campo);
    }
    if (!valido(valor)) throw campoInvalido(campo);
    dados[campo] = valor;
  }
  return dados;
}

const INT4_MIN = -2147483648n;
const INT4_MAX = 2147483647n;

// Devolve o id como número, ou null se não cabe na coluna SERIAL (logo, não existe).
export function validarId(texto) {
  if (!/^-?[0-9]+$/.test(texto)) throw campoInvalido("id");
  const id = BigInt(texto);
  if (id < INT4_MIN || id > INT4_MAX) return null;
  return Number(id);
}
