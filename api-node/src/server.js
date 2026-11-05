import express from "express";

import { pool } from "./db.js";
import { errorHandler } from "./errorHandler.js";
import { router as health } from "./routes/health.js";
import { router as users } from "./routes/users.js";

const PORT = Number(process.env.PORT ?? 8000);

const app = express();
app.disable("x-powered-by");
app.disable("etag");

// O corpo é lido como texto e o JSON.parse é feito na validação,
// para devolver o mesmo erro 400 das outras APIs.
app.use(express.text({ type: () => true, limit: "1mb" }));

app.use(health);
app.use(users);
app.use(errorHandler);

await pool.query("SELECT 1"); // falha logo na subida se o banco não estiver acessível
app.listen(PORT, "0.0.0.0", () => console.log(`API Node ouvindo na porta ${PORT}`));
