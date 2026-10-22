from datetime import date
from app.db import pool

# O próprio Postgres formata datas como texto: assim as 4 APIs devolvem
# exatamente o mesmo formato, sem depender de cada linguagem.

COLUNAS = """
    id,
    name,
    email,
    to_char(birthday, 'YYYY-MM-DD') AS birthday,
    cpf,
    to_char(inserted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), AS inserted_at,
    to_char(updated_at  AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at
"""

def criar(name: str, email:str, birthday: date, cpf:str) -> dict:
    with pool.connection() as conn:
        return conn.execute(
             f"""INSERT INTO users (name, email, birthday, cpf)
                VALUES (%s, %s, %s, %s)
                RETURNING {COLUNAS}""",
            (name, email, birthday, cpf),
        ).fetchone()
        
def listar() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(f"SELECT {COLUNAS} FROM users ORDER BY id").fetchall()
        
        
def buscar_por_id(user_id: int) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            f"SELECT {COLUNAS} FROM users WHERE id =%s", (user_id,),
        ).fetchone()
        
def buscar_por_id(user_id: int) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            f"SELECT {COLUNAS} FROM users WHERE id = %s", (user_id,)
        ).fetchone()

def atualizar(user_id: int, name: str, email: str, birthday: date, cpf: str) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            f"""UPDATE users
                SET name = %s, email = %s, birthday = %s, cpf = %s
                WHERE id = %s
                RETURNING {COLUNAS}""",
            (name, email, birthday, cpf, user_id),
        ).fetchone()
        
def atualizar_parcial(
    user_id: int,
    name: str | None,
    email: str | None,
    birthday: date | None,
    cpf: str | None,
) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            f"""UPDATE users
                SET name = COALESCE(%s, name),
                    email    = COALESCE(%s, email),
                    birthday = COALESCE(%s, birthday),
                    cpf      = COALESCE(%s, cpf)
                WHERE id = %s
                RETURNING {COLUNAS}""",
                (name, email, birthday, cpf, user_id),
        ).fetchone()


def remover(user_id: int) -> bool:
    with pool.connection() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        return cursor.rowcount > 0