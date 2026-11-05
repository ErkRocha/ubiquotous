package main

import (
	"context"
	"log"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		databaseURL = "postgresql://postgres:postgres@localhost:5432/users_db"
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		log.Fatalf("config do banco inválida: %v", err)
	}
	defer pool.Close()
	// falha logo na subida se o banco não estiver acessível
	if err := pool.Ping(ctx); err != nil {
		log.Fatalf("não foi possível conectar no banco: %v", err)
	}

	h := &handlers{models: &models{pool: pool}}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", h.health)
	mux.HandleFunc("POST /users", h.criar)
	mux.HandleFunc("GET /users", h.listar)
	mux.HandleFunc("GET /users/{id}", h.buscar)
	mux.HandleFunc("PUT /users/{id}", h.substituir)
	mux.HandleFunc("PATCH /users/{id}", h.atualizarParcial)
	mux.HandleFunc("DELETE /users/{id}", h.remover)

	log.Printf("API Go ouvindo na porta %s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
