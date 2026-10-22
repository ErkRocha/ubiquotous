import pg from "pg";

const DATABASE_URL =
  process.env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/users_db";

export const pool = new pg.Pool({ connectionString: DATABASE_URL });
