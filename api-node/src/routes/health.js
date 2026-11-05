import { Router } from "express";

import { pool } from "../db.js";

export const router = Router();

router.get("/health", async (req, res) => {
  try {
    await Promise.race([
      pool.query("SELECT 1"),
      new Promise((_, rejeitar) => setTimeout(() => rejeitar(new Error("timeout")), 2000).unref()),
    ]);
    res.status(200).json({ status: "ok", database: "up" });
  } catch {
    res.status(503).json({ status: "error", database: "down" });
  }
});
