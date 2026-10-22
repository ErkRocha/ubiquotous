CREATE TABLE IF NOT EXISTS users (
    id  SERIAL  PRIMARY KEY,
    name    TEXT    NOT NULL,
    email   TEXT    NOT NULL,
    birthday    DATE         NOT NULL,
    cpf         VARCHAR(11)  NOT NULL,
    inserted_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT users_email_key UNIQUE (email),
    CONSTRAINT users_cpf_key   UNIQUE (cpf)
);

CREATE OR REPLACE FUNCTION set_update_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    