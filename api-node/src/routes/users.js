import { Router } from "express";

import * as models from "../models.js";
import { naoEncontrado } from "../errors.js";
import { lerCorpo, validarId, validarUsuario } from "../validacao.js";

export const router = Router();

function idOu404(req) {
  const id = validarId(req.params.id);
  if (id === null) throw naoEncontrado();
  return id;
}

router.post("/users", async (req, res) => {
  const dados = validarUsuario(lerCorpo(req), false);
  const usuario = await models.criar(dados);
  res.status(201).location(`/users/${usuario.id}`).json(usuario);
});

router.get("/users", async (req, res) => {
  res.json(await models.listar());
});

router.get("/users/:id", async (req, res) => {
  const usuario = await models.buscarPorId(idOu404(req));
  if (!usuario) throw naoEncontrado();
  res.json(usuario);
});

router.put("/users/:id", async (req, res) => {
  const id = idOu404(req);
  const dados = validarUsuario(lerCorpo(req), false);
  const usuario = await models.atualizar(id, dados);
  if (!usuario) throw naoEncontrado();
  res.json(usuario);
});

router.patch("/users/:id", async (req, res) => {
  const id = idOu404(req);
  const dados = validarUsuario(lerCorpo(req), true);
  const usuario = await models.atualizarParcial(id, dados);
  if (!usuario) throw naoEncontrado();
  res.json(usuario);
});

router.delete("/users/:id", async (req, res) => {
  if (!(await models.remover(idOu404(req)))) throw naoEncontrado();
  res.status(204).end();
});
