# SLG Agro - Silos PWA (Flask + React CDN) — listo para Render

Monorepo simple: un servicio web (Flask) que sirve API + frontend React (sin build) y PWA.

## Stack
- Backend: Flask + SQLAlchemy (PostgreSQL en prod, SQLite fallback en local)
- Frontend: React + Tailwind vía CDN (sin toolchain), PWA (manifest + service worker)
- Deploy: Render (un único servicio Python).

## Variables
- `DATABASE_URL` (Render): URL de Postgres. Si no está, usa SQLite `backend/silos.db`.
- `FLASK_ENV=production`

## Ejecutar local
```bash
python -m venv .venv
source .venv/bin/activate  # en Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
export FLASK_RUN_PORT=5000
python backend/app.py
# Abre http://localhost:5000
```

## Deploy en Render
1. Sube este repo a GitHub.
2. En Render: "New +", "Web Service", conecta el repo.
3. Runtime: **Python**.
4. Build Command: `pip install -r backend/requirements.txt`
5. Start Command: `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT`
6. Env vars: agrega `DATABASE_URL` apuntando a tu Postgres (Render Postgres addon).
7. Deploy.

## Endpoints clave
- `GET /api/silos` listar
- `POST /api/silos` crear `{name}` (único). Muestra notificación en UI.
- `PATCH /api/silos/<id>` renombrar `{name}`
- `DELETE /api/silos/<id>` eliminar
- `POST /api/silos/<id>/cargar` `{amount, cereal?}` (si el silo está vacío y sin cereal, es obligatorio)
- `POST /api/silos/<id>/descargar` `{amount}` (controla no negativo)
- `GET /api/resumen` movimientos con fecha y hora (sin segundos)

PWA: manifest y service worker ya incluidos.
