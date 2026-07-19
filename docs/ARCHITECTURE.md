# Arquitectura

## Estilo

Arquitectura hexagonal con DDD ligero. El dominio no importa frameworks; la
infraestructura implementa los puertos; la capa de aplicación orquesta casos de
uso; la API es un adaptador de entrada más.

```
        ┌───────────────────────────── adaptadores de entrada ──┐
        │  FastAPI (REST)      Celery beat/workers (tiempo)     │
        └────────────┬──────────────────────┬───────────────────┘
                     ▼                      ▼
        ┌──────────────────── application ─────────────────────┐
        │ ingestion · prediction_service · parlay_service ·    │
        │ results_service · context_builder                    │
        └────────────┬──────────────────────┬──────────────────┘
                     ▼                      ▼
        ┌── domain ────────────┐  ┌── ml (EVR Engine) ─────────┐
        │ entities (Odds, Edge,│  │ features · model_zoo ·     │
        │ Market, Candidate)   │  │ elo · monte_carlo ·        │
        │ events (pub/sub)     │  │ bayesian · engine ·        │
        └──────────────────────┘  │ player_props · training    │
                     ▲            └────────────────────────────┘
        ┌────────────┴───────── infrastructure ────────────────┐
        │ db (SQLAlchemy) · cache (Redis) · providers (HTTP)   │
        └──────────────────────────────────────────────────────┘
```

## Decisiones clave

- **CQRS pragmático**: las lecturas de la API golpean proyecciones simples
  (tablas `predictions`, `parlays`, `engine_metrics`) que los workers escriben;
  los comandos (jobs) van por Celery. No hay bus de comandos formal porque el
  dominio no lo amerita todavía.
- **Event-driven**: los cambios detectados en la ingestión (lineup confirmado,
  cambio de pitcher, juego final) se publican como eventos de dominio en Redis
  (pub/sub + cola durable). Un task los drena y dispara recomputación inmediata
  del juego afectado — sin esperar al siguiente tick de 2 minutos.
- **Idempotencia**: regenerar predicciones actualiza la fila
  (game_pk, market, selection) en lugar de duplicar; liquidar es terminal
  (una predicción settled no se reescribe).
- **Cold start honesto**: sin histórico, el ensemble opera con los votantes
  analíticos (Monte Carlo + ELO + modelos de tasas). El zoo ML entra al blend
  cuando acumula ≥120 ejemplos liquidados por familia de mercado, y sus pesos
  los decide la recalibración bayesiana, no una constante.
- **Fail-open en infraestructura auxiliar**: rate limiter y caché degradan a
  no-op si Redis no responde; un proveedor caído reporta estado `down` y el
  resto del pipeline continúa.

## Flujo de datos (día típico)

1. **06:00 UTC** `bootstrap_reference_data`: equipos, cartelera, rosters.
2. **Cada 2 min** `refresh_all_data`: schedule/lineups/scores → odds → clima →
   `generate_predictions` → eventos.
3. **Cada 15 min** `build_parlays`: reconstruye los 6 perfiles desde el pool.
4. **Cada 30 min** `refresh_slate_stats`: stats de todos los jugadores del día.
5. **En vivo** eventos de lineup/pitcher recomputan el juego afectado al
   instante; juegos finales se liquidan sin esperar la noche.
6. **08:30 UTC** `close_previous_day`: liquidación completa + recalibración
   bayesiana + ELO + reentrenamiento + métricas. El ciclo de aprendizaje
   completo, sin humanos.

## Modelo de datos (resumen)

- Identidad: `users`, `refresh_tokens`, `subscriptions`, `payments`, `audit_logs`
- Béisbol: `teams` (con ELO), `players`, `player_stats` (snapshots por scope),
  `bullpen_stats`, `park_factors`, `umpires`
- Mercado: `games`, `odds_quotes` (cada captura, para line movement)
- Motor: `predictions` (con features, breakdown por modelo, EV/edge/Kelly),
  `parlays`, `model_weights`, `engine_metrics`, `api_source_status`
- Usuario: `bankrolls`, `bets`

## Escalado

Cada servicio del compose escala horizontalmente: más `worker` para slates
grandes, más réplicas de `backend` tras NGINX. El estado vive en Postgres/Redis;
los artefactos de modelos en el volumen `models-store` (en AWS: EFS o S3 +
descarga al boot). Ver `docs/DEPLOYMENT.md`.
