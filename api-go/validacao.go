package main

import (
	"encoding/json"
	"io"
	"math"
	"mime"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

// Mesmas regras do schemas.py da API Python.
// O \s do Go só pega espaço ASCII; [\x{09}-\x{0D}\x{85}\p{Z}] é o \s Unicode do Python/Rust.
var (
	reEmail = regexp.MustCompile(`^[^@\x{09}-\x{0D}\x{85}\p{Z}]+@[^@\x{09}-\x{0D}\x{85}\p{Z}]+\.[^@\x{09}-\x{0D}\x{85}\p{Z}]+$`)
	reCpf   = regexp.MustCompile(`^[0-9]{11}$`)
	reData  = regexp.MustCompile(`^[0-9]{4}-[0-9]{2}-[0-9]{2}$`)
	reID    = regexp.MustCompile(`^-?[0-9]+$`)
)

// Campos validados. nil = não enviado (só acontece no PATCH).
type dadosUsuario struct {
	Name     *string
	Email    *string
	Birthday *time.Time
	Cpf      *string
}

func texto(v any, valido func(string) bool) (*string, bool) {
	s, ok := v.(string)
	if !ok || !valido(s) {
		return nil, false
	}
	return &s, true
}

// O corpo precisa ser um objeto JSON.
func lerCorpo(r *http.Request) (map[string]any, *ApiError) {
	if ct := r.Header.Get("Content-Type"); ct != "" {
		tipo, _, err := mime.ParseMediaType(ct)
		if err != nil || !(tipo == "application/json" ||
			(strings.HasPrefix(tipo, "application/") && strings.HasSuffix(tipo, "+json"))) {
			return nil, corpoInvalido()
		}
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil || len(body) == 0 {
		return nil, corpoInvalido()
	}
	var corpo map[string]any
	if err := json.Unmarshal(body, &corpo); err != nil || corpo == nil {
		return nil, corpoInvalido()
	}
	return corpo, nil
}

// parcial = false (POST/PUT): todos os campos obrigatórios.
// parcial = true (PATCH): campo ausente ou null é ignorado.
func validarUsuario(corpo map[string]any, parcial bool) (dadosUsuario, *ApiError) {
	var d dadosUsuario
	var ok bool

	for _, campo := range []string{"name", "email", "birthday", "cpf"} {
		valor := corpo[campo] // ausente ou null -> nil
		if valor == nil {
			if parcial {
				continue
			}
			return d, campoInvalido(campo)
		}

		switch campo {
		case "name":
			d.Name, ok = texto(valor, func(s string) bool { return utf8.RuneCountInString(s) >= 1 })
		case "email":
			d.Email, ok = texto(valor, reEmail.MatchString)
		case "birthday":
			d.Birthday, ok = data(valor)
		case "cpf":
			d.Cpf, ok = texto(valor, reCpf.MatchString)
		}
		if !ok {
			return d, campoInvalido(campo)
		}
	}
	return d, nil
}

func data(v any) (*time.Time, bool) {
	s, ok := v.(string)
	if !ok || !reData.MatchString(s) {
		return nil, false
	}
	t, err := time.Parse(time.DateOnly, s)
	if err != nil || t.Year() < 1 {
		return nil, false
	}
	return &t, true
}

// Devolve o id; existe = false se ele não cabe na coluna SERIAL (logo, não existe).
func validarID(r *http.Request) (id int32, existe bool, apiErr *ApiError) {
	valor := r.PathValue("id")
	if !reID.MatchString(valor) {
		return 0, false, campoInvalido("id")
	}
	n, err := strconv.ParseInt(valor, 10, 64)
	if err != nil || n < math.MinInt32 || n > math.MaxInt32 {
		return 0, false, nil
	}
	return int32(n), true, nil
}
