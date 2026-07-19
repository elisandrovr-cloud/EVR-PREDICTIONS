# Despliegue en Vercel (frontend + backend en un solo proyecto)

`vercel.json` en la raíz declara **dos servicios** en un mismo despliegue:

- **Frontend** — la app Next.js en `frontend/` (`@vercel/next`).
- **Backend** — la API FastAPI expuesta como función serverless Python
  (`@vercel/python`) desde `backend/api/index.py`, que reexporta la app ASGI.

Las `routes` enrutan `/api/*`, `/docs`, `/redoc` y `/openapi.json` a la función
Python; todo lo demás va al frontend. Al ser el mismo origen, el frontend sigue
usando `NEXT_PUBLIC_API_URL=/api/v1` sin CORS.

## Variables de entorno (Project → Settings → Environment Variables)

Vercel no ejecuta Postgres, Redis ni procesos de larga duración: usa servicios
gestionados.

| Variable | Valor |
|---|---|
| `DATABASE_URL` | Postgres gestionado (Neon, Supabase, RDS). `postgresql+psycopg2://…` |
| `REDIS_URL` | Redis gestionado (Upstash). Opcional: sin él, rate-limit y caché degradan a no-op |
| `SECRET_KEY` | 64 hex aleatorios |
| `CRON_SECRET` | Secreto para los cron jobs. **Vercel lo inyecta** como `Authorization: Bearer <CRON_SECRET>` |
| `MODELS_STORE_DIR` | `/tmp/models` (único directorio escribible en serverless) |
| `ODDS_API_KEY`, `OPENWEATHER_API_KEY` | Opcionales, activan cuotas y clima |
| `NEXT_PUBLIC_API_URL` | `/api/v1` |

## Cron: reemplaza a Celery beat

El bloque `crons` de `vercel.json` sustituye el `beat` del contenedor. Cada
entrada hace un GET al endpoint protegido `/api/v1/cron/{job}`:

| Path | Schedule | Equivalente |
|---|---|---|
| `/api/v1/cron/refresh` | `*/2 * * * *` | tick de 2 min (schedule + odds + clima + predicciones + parlays) |
| `/api/v1/cron/stats` | `*/30 * * * *` | stats del slate |
| `/api/v1/cron/bootstrap` | `0 6 * * *` | equipos + cartelera |
| `/api/v1/cron/close-day` | `30 8 * * *` | cierre nocturno con aprendizaje |

`cron_runner.py` ejecuta cada job de forma **síncrona** (sin broker), así que no
hace falta un worker. La primera vez, dispara `bootstrap` manualmente:
`curl -H "Authorization: Bearer $CRON_SECRET" https://TU-APP.vercel.app/api/v1/cron/bootstrap`.

## Límites reales que debes conocer

- **Frecuencia de cron**: `*/2` (cada 2 min) requiere plan **Pro**; en Hobby el
  mínimo es diario. Ajusta el schedule según tu plan.
- **Timeout de función**: 10 s (Hobby) / 60 s (Pro) / hasta 300 s configurable.
  Un `refresh` sobre una cartelera completa puede acercarse al límite; si lo
  supera, reduce el alcance por tick o usa el path de contenedor para el motor.
- **Tamaño de la función (250 MB)**: el motor ML carga `scikit-learn`, `numpy`,
  `pandas` y opcionalmente XGBoost/LightGBM/CatBoost. Con las cuatro librerías de
  boosting el paquete puede exceder el límite. Opciones: (a) confiar en los
  fallbacks de `scikit-learn` que ya trae el zoo y omitir XGBoost/LightGBM/
  CatBoost del `requirements`, o (b) mantener el **motor pesado en un host de
  contenedores** (ver `docs/DEPLOYMENT.md`) y usar Vercel solo para el frontend
  + API ligera, apuntando `DATABASE_URL` a la misma base.

## Recomendación

Vercel es ideal para el **frontend** y una **API de lectura**. Para el pipeline
de entrenamiento continuo (workers siempre activos, reentrenamiento nocturno con
las librerías completas) el despliegue en contenedores de `docs/DEPLOYMENT.md`
sigue siendo el camino de producción del motor completo; ambos pueden compartir
la misma Postgres/Redis gestionada.
