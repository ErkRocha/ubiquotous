package main

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Mesmo SQL da API Python: o Postgres formata as datas,
// então as 4 APIs devolvem exatamente o mesmo formato.
const colunas = `
    id,
    name,
    email,
    to_char(birthday, 'YYYY-MM-DD') AS birthday,
    cpf,
    to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS inserted_at,
    to_char(updated_at  AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at
`

// A ordem dos campos aqui é a ordem no JSON de resposta.
type Usuario struct {
	ID         int32  `json:"id"`
	Name       string `json:"name"`
	Email      string `json:"email"`
	Birthday   string `json:"birthday"`
	Cpf        string `json:"cpf"`
	InsertedAt string `json:"inserted_at"`
	UpdatedAt  string `json:"updated_at"`
}

type models struct {
	pool *pgxpool.Pool
}

func scanUsuario(row pgx.Row) (*Usuario, error) {
	var u Usuario
	err := row.Scan(&u.ID, &u.Name, &u.Email, &u.Birthday, &u.Cpf, &u.InsertedAt, &u.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (m *models) criar(ctx context.Context, d dadosUsuario) (*Usuario, error) {
	return scanUsuario(m.pool.QueryRow(ctx,
		`INSERT INTO users (name, email, birthday, cpf)
		 VALUES ($1, $2, $3, $4)
		 RETURNING `+colunas,
		d.Name, d.Email, d.Birthday, d.Cpf))
}

func (m *models) listar(ctx context.Context) ([]Usuario, error) {
	rows, err := m.pool.Query(ctx, `SELECT `+colunas+` FROM users ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	usuarios := []Usuario{} // lista vazia vira [] no JSON, e não null
	for rows.Next() {
		u, err := scanUsuario(rows)
		if err != nil {
			return nil, err
		}
		usuarios = append(usuarios, *u)
	}
	return usuarios, rows.Err()
}

func (m *models) buscarPorID(ctx context.Context, id int32) (*Usuario, error) {
	return scanUsuario(m.pool.QueryRow(ctx, `SELECT `+colunas+` FROM users WHERE id = $1`, id))
}

func (m *models) atualizar(ctx context.Context, id int32, d dadosUsuario) (*Usuario, error) {
	return scanUsuario(m.pool.QueryRow(ctx,
		`UPDATE users
		 SET name = $1, email = $2, birthday = $3, cpf = $4
		 WHERE id = $5
		 RETURNING `+colunas,
		d.Name, d.Email, d.Birthday, d.Cpf, id))
}

func (m *models) atualizarParcial(ctx context.Context, id int32, d dadosUsuario) (*Usuario, error) {
	return scanUsuario(m.pool.QueryRow(ctx,
		`UPDATE users
		 SET name     = COALESCE($1, name),
		     email    = COALESCE($2, email),
		     birthday = COALESCE($3, birthday),
		     cpf      = COALESCE($4, cpf)
		 WHERE id = $5
		 RETURNING `+colunas,
		d.Name, d.Email, d.Birthday, d.Cpf, id))
}

func (m *models) remover(ctx context.Context, id int32) (bool, error) {
	tag, err := m.pool.Exec(ctx, `DELETE FROM users WHERE id = $1`, id)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}
