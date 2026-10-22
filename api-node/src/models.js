import { pool } from "./db.js";

// Mesmo SQL da API Python: o Postgres formata as datas,
// então as 4 APIs devolvem exatamente o mesmo formato.
const COLUNAS = `
    id,
    name,
    email,
    to_char(birthday, 'YYYY-MM-DD') AS birthday,
    cpf,
    to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS inserted_at,
    to_char(updated_at  AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at
`;

export async function criar({ name, email, birthday, cpf }) {
  const { rows } = await pool.query(
    `INSERT INTO users (name, email, birthday, cpf)
     VALUES ($1, $2, $3, $4)
     RETURNING ${COLUNAS}`,
    [name, email, birthday, cpf],
  );
  return rows[0];
}

export async function listar() {
  const { rows } = await pool.query(`SELECT ${COLUNAS} FROM users ORDER BY id`);
  return rows;
}

export async function buscarPorId(id) {
  const { rows } = await pool.query(`SELECT ${COLUNAS} FROM users WHERE id = $1`, [id]);
  return rows[0] ?? null;
}

export async function atualizar(id, { name, email, birthday, cpf }) {
  const { rows } = await pool.query(
    `UPDATE users
     SET name = $1, email = $2, birthday = $3, cpf = $4
     WHERE id = $5
     RETURNING ${COLUNAS}`,
    [name, email, birthday, cpf, id],
  );
  return rows[0] ?? null;
}

export async function atualizarParcial(id, { name, email, birthday, cpf }) {
  const { rows } = await pool.query(
    `UPDATE users
     SET name     = COALESCE($1, name),
         email    = COALESCE($2, email),
         birthday = COALESCE($3, birthday),
         cpf      = COALESCE($4, cpf)
     WHERE id = $5
     RETURNING ${COLUNAS}`,
    [name ?? null, email ?? null, birthday ?? null, cpf ?? null, id],
  );
  return rows[0] ?? null;
}

export async function remover(id) {
  const { rowCount } = await pool.query("DELETE FROM users WHERE id = $1", [id]);
  return rowCount > 0;
}
