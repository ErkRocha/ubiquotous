package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"

	"github.com/jackc/pgx/v5/pgconn"
)

type ApiError struct {
	Status  int
	Code    string
	Message string
}

func naoEncontrado() *ApiError {
	return &ApiError{404, "NOT_FOUND", "Usuário não encontrado."}
}

func campoInvalido(campo string) *ApiError {
	return &ApiError{400, "VALIDATION_ERROR", fmt.Sprintf("O campo '%s' é inválido ou está ausente.", campo)}
}

func corpoInvalido() *ApiError {
	return &ApiError{400, "VALIDATION_ERROR", "Corpo da requisição ausente ou com JSON inválido."}
}

// nome da constraint no banco (db/init.sql) -> erro devolvido pela API
var conflitos = map[string]*ApiError{
	"users_email_key": {409, "EMAIL_IN_USE", "Este e-mail já está cadastrado."},
	"users_cpf_key":   {409, "CPF_IN_USE", "Este CPF já está cadastrado."},
}

// Converte erro do banco em resposta: UNIQUE vira 409, o resto vira 500.
func erroDoBanco(err error) *ApiError {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		if e, ok := conflitos[pgErr.ConstraintName]; ok {
			return e
		}
		return &ApiError{409, "CONFLICT", "Registro duplicado."}
	}
	log.Printf("Erro não tratado: %v", err)
	return &ApiError{500, "INTERNAL_ERROR", "Erro interno do servidor."}
}

func responderJSON(w http.ResponseWriter, status int, v any) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false) // não troca < > & por < etc., igual às outras APIs
	if err := enc.Encode(v); err != nil {
		log.Printf("Erro ao gerar JSON: %v", err)
		status = 500
		buf.Reset()
		buf.WriteString(`{"error":{"code":"INTERNAL_ERROR","message":"Erro interno do servidor."}}`)
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write(bytes.TrimRight(buf.Bytes(), "\n"))
}

func responderErro(w http.ResponseWriter, e *ApiError) {
	responderJSON(w, e.Status, map[string]any{
		"error": map[string]string{"code": e.Code, "message": e.Message},
	})
}
