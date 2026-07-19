# Despliegue en Vercel (proyecto multi-service)

Vercel reconoce el monorepo como **proyecto con múltiples servicios** mediante el
bloque `services` de `vercel.json` (raíz). Este es el formato que activa la
opción de deploy en el dashboard; el formato legacy `builds`/`routes` **no** la
activa.

## Estructura

**`vercel.json` (raíz)** declara dos servicios y el enrutado entre ellos:

```json
{
  "services": {
    "frontend": { "root": "frontend", "framework": "nextjs" },
    "backend":  { "root": "backend" }
  },
  "rewrites": [
    { "source": "/api/(.*)",     "destination": { "type": "service", "service": "backend" } },
    { "source": "/docs(.*)",     "destination": { "type": "service", "service": "backend" } },
    { "source": "/redoc(.*)",    "destination": { "type": "service", "service": "backend" } },
    { "source": "/openapi.json", "destination": { "type": "service", "service": "backend" } },
    { "source": "/(.*)",         "destination": { "type": "service", "service": "frontend" } }
  ]
}
```

- `frontend` (root `frontend/`, framework Next.js) recibe todo lo que no es API.
- `backend` (root `backend/`) recibe `/api/*`, `/docs`, `/redoc`, `/openapi.json`.
  Vercel lo detecta como funciones serverless Python por `backend/api/index.py`
  (que reexporta la app FastAPI) + `backend/api/requirements.txt`.

> **Por qué `/api/(.*)` y no `/api/backend`:** el frontend llama a
> `NEXT_PUBLIC_API_URL=/api/v1`, así que todo `/api/*` debe ir al backend. El
> prefijo `/api/backend` de la plantilla no coincidía con esas llamadas.

**`backend/vercel.json`** enruta internamente todas las rutas del servicio a la
única función ASGI, para que FastAPI haga su propio ruteo (`/api/v1/...`, `/docs`)
y agenda los cron:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }],
  "crons": [ … ]
}
```

## Dependencias serverless más ligeras

`backend/api/requirements.txt` (adyacente a la función, tiene prioridad en Vercel)
**omite XGBoost, LightGBM, CatBoost y pandas** para caber en el límite de 250 MB
de una función serverless. El zoo de modelos ya cae a `GradientBoosting` de
scikit-learn cuando esas librerías faltan (`app/ml/model_zoo.py`), así que se
siguen produciendo los 8 votos del ensemble — con implementaciones sklearn.
El Docker sigue usando el `backend/requirements.txt` completo (con los boosters).

## Variables de entorno (Project → Settings → Environment Variables)

| Variable | Valor |
|---|---|
| `DATABASE_URL` | Postgres gestionado (Neon, Supabase, RDS) `postgresql+psycopg2://…` |
| `REDIS_URL` | Redis gestionado (Upstash). Opcional: sin él, rate-limit y caché degradan a no-op |
| `SECRET_KEY` | 64 hex aleatorios |
| `CRON_SECRET` | Secreto de cron. **Vercel lo inyecta** como `Authorization: Bearer <CRON_SECRET>` |
| `MODELS_STORE_DIR` | `/tmp/models` (único directorio escribible en serverless) |
| `ODDS_API_KEY`, `OPENWEATHER_API_KEY` | Opcionales (cuotas y clima) |
| `NEXT_PUBLIC_API_URL` | `/api/v1` (en el servicio frontend) |

## Cron (reemplaza a Celery beat)

Definido en `backend/vercel.json`. Cada entrada hace un GET a
`/api/v1/cron/{job}`, protegido por `CRON_SECRET`, ejecutado de forma síncrona
por `app/application/cron_runner.py` (sin broker):

| Path | Schedule | Job |
|---|---|---|
| `/api/v1/cron/refresh` | `*/2 * * * *` | schedule + odds + clima + predicciones + parlays |
| `/api/v1/cron/stats` | `*/30 * * * *` | stats del slate |
| `/api/v1/cron/bootstrap` | `0 6 * * *` | equipos + cartelera |
| `/api/v1/cron/close-day` | `30 8 * * *` | cierre nocturno con aprendizaje |

Primer arranque: `curl -H "Authorization: Bearer $CRON_SECRET" https://TU-APP.vercel.app/api/v1/cron/bootstrap`.

## Límites a tener en cuenta

- **Frecuencia de cron:** `*/2` (cada 2 min) requiere plan **Pro**; en Hobby el
  mínimo es diario. Ajusta el schedule según tu plan.
- **Timeout de función:** 10 s (Hobby) / 60 s (Pro) / hasta 300 s configurable.
  Un `refresh` de una cartelera completa puede acercarse al límite.
- **Si el dashboard rechaza `crons` junto a `services`:** mueve el bloque `crons`
  a la `vercel.json` raíz (mismos paths); el ruteo a backend lo resuelven los
  `rewrites` de nivel superior.

## Si la app aparece vacía (sin juegos ni predicciones)

En serverless no hay worker que llene la base, así que hay dos requisitos y un
diagnóstico:

1. **`DATABASE_URL` debe apuntar a un Postgres gestionado.** SQLite no persiste
   entre invocaciones serverless; sin una base real, cada request arranca vacío.
2. **Auto-seed** (activado por defecto, `AUTO_SEED=true`): la primera vez que el
   frontend pide `/games/today` o `/predictions/daily`, si la base está vacía el
   backend trae la cartelera del día y genera las predicciones de juego en esa
   misma petición. No hace falta cron ni trigger manual para ver datos.
3. **Diagnóstico:** abre `https://TU-APP.vercel.app/api/v1/health`. Devuelve:
   - `database.connected` — si es `false`, falta o está mal `DATABASE_URL`.
   - `database.games_today` / `predictions_today` — cuántos datos hay.
   - `config.cron_enabled` / `odds_enabled` / `weather_enabled` — qué integraciones están activas.
   - `hint` — el siguiente paso concreto según lo que falte.

> El auto-seed genera predicciones **a nivel de juego** (moneyline, run line,
> over/under, primera entrada) usando promedios de liga si aún no hay stats. Los
> props de jugador y las stats reales los rellena el cron `stats`/`refresh` (o
> `refresh_slate_stats` en el contenedor) en cuanto corre.

## Recomendación

Vercel es ideal para el **frontend + API de lectura y cron**. Para el pipeline
de entrenamiento continuo con las librerías de boosting completas y workers
siempre activos, el despliegue en contenedores de `docs/DEPLOYMENT.md` sigue
siendo el camino de producción del motor completo; ambos pueden compartir la
misma Postgres/Redis gestionada.
