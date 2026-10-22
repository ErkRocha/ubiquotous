package main

import (
	"fmt"
	"net/http"
)

type handlers struct {
	models *models
}

// Lê e valida o id da rota. Devolve false se já respondeu (400 ou 404).
func idDaRota(w http.ResponseWriter, r *http.Request) (int32, bool) {
	id, existe, apiErr := validarID(r)
	if apiErr != nil {
		responderErro(w, apiErr)
		return 0, false
	}
	if !existe {
		responderErro(w, naoEncontrado())
		return 0, false
	}
	return id, true
}

// Lê e valida o corpo. Devolve false se já respondeu 400.
func corpoDoUsuario(w http.ResponseWriter, r *http.Request, parcial bool) (dadosUsuario, bool) {
	corpo, apiErr := lerCorpo(r)
	if apiErr == nil {
		var d dadosUsuario
		if d, apiErr = validarUsuario(corpo, parcial); apiErr == nil {
			return d, true
		}
	}
	responderErro(w, apiErr)
	return dadosUsuario{}, false
}

// Responde o usuário, 404 se ele não existe, ou o erro do banco.
func responderUsuario(w http.ResponseWriter, u *Usuario, err error) {
	switch {
	case err != nil:
		responderErro(w, erroDoBanco(err))
	case u == nil:
		responderErro(w, naoEncontrado())
	default:
		responderJSON(w, http.StatusOK, u)
	}
}

func (h *handlers) criar(w http.ResponseWriter, r *http.Request) {
	d, ok := corpoDoUsuario(w, r, false)
	if !ok {
		return
	}
	u, err := h.models.criar(r.Context(), d)
	if err != nil {
		responderErro(w, erroDoBanco(err))
		return
	}
	w.Header().Set("Location", fmt.Sprintf("/users/%d", u.ID))
	responderJSON(w, http.StatusCreated, u)
}

func (h *handlers) listar(w http.ResponseWriter, r *http.Request) {
	usuarios, err := h.models.listar(r.Context())
	if err != nil {
		responderErro(w, erroDoBanco(err))
		return
	}
	responderJSON(w, http.StatusOK, usuarios)
}

func (h *handlers) buscar(w http.ResponseWriter, r *http.Request) {
	id, ok := idDaRota(w, r)
	if !ok {
		return
	}
	u, err := h.models.buscarPorID(r.Context(), id)
	responderUsuario(w, u, err)
}

func (h *handlers) substituir(w http.ResponseWriter, r *http.Request) {
	id, ok := idDaRota(w, r)
	if !ok {
		return
	}
	d, ok := corpoDoUsuario(w, r, false)
	if !ok {
		return
	}
	u, err := h.models.atualizar(r.Context(), id, d)
	responderUsuario(w, u, err)
}

func (h *handlers) atualizarParcial(w http.ResponseWriter, r *http.Request) {
	id, ok := idDaRota(w, r)
	if !ok {
		return
	}
	d, ok := corpoDoUsuario(w, r, true)
	if !ok {
		return
	}
	u, err := h.models.atualizarParcial(r.Context(), id, d)
	responderUsuario(w, u, err)
}

func (h *handlers) remover(w http.ResponseWriter, r *http.Request) {
	id, ok := idDaRota(w, r)
	if !ok {
		return
	}
	removido, err := h.models.remover(r.Context(), id)
	switch {
	case err != nil:
		responderErro(w, erroDoBanco(err))
	case !removido:
		responderErro(w, naoEncontrado())
	default:
		w.WriteHeader(http.StatusNoContent)
	}
}
