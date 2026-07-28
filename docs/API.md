# API REST

Documentación interactiva: **`/docs`** (Swagger UI) y **`/redoc`**. Prefijo:
`/api/v1`. Autenticación: `Authorization: Bearer <access_token>`.

## Auth

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/register` | Alta con email/contraseña → par de tokens |
| POST | `/auth/login` | Login → par de tokens |
| POST | `/auth/refresh` | Rota el refresh token (un solo uso) |
| GET | `/auth/me` | Perfil del usuario autenticado |
| GET | `/auth/oauth/{google\|github}/login` | Redirección OAuth |
| GET | `/auth/oauth/{provider}/callback` | Intercambio de código → tokens |

## Agentes IA (multi-agente)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/agents/status` | Estado del último run de cada uno de los 8 agentes |
| GET | `/agents/roster` | El equipo de agentes y sus especialidades |
| GET | `/agents/last-cycle` | Último ciclo de monitoreo + marca de "última actualización" |
| POST | `/agents/refresh` | **ACTUALIZAR AHORA** — ciclo completo síncrono (`?only=` para un subconjunto) |
| GET | `/agents/changes` | Historial de movimientos (`severity`, `change_type`, `limit`) |
| GET | `/agents/news` | Feed de noticias y lesiones (`category`) |
| POST | `/agents/chat` | Preguntar al Supervisor → respuesta única justificada |
| GET | `/agents/chat/history` | Transcripción de la conversación |

Detalle completo en [`MULTI_AGENT.md`](MULTI_AGENT.md).

## Jugadores

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/players?kind=batters\|pitchers\|all` | Directorio con `q`, `team_mlb_id`, `status`, `sort`, `order`, `limit`, `offset` |
| GET | `/players/search?q=` | Autocompletado |
| GET | `/players/{mlb_id}/profile` | Perfil completo: bio, foto, stats, últimos 5 juegos, props de hoy, noticias y movimientos |
| GET | `/players/{mlb_id}/stats` | Snapshots crudos por scope |
| GET | `/players/compare?ids=1,2,3` | Comparación lado a lado (2–4 jugadores) |

## Cuotas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/odds/books` | Proveedores de cuotas disponibles y cuál está activo |
| POST | `/odds/manual` | Cargar una línea vista en tu casa de apuestas (Hard Rock Bet por defecto) y re-valorar la selección |
| GET | `/odds/today` | Cuotas capturadas hoy |

## Juegos

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/games/today` | Cartelera de hoy (lineups, clima, umpire, marcador) |
| GET | `/games/live` | Juegos en vivo |
| GET | `/games/calendar/{YYYY-MM-DD}` | Cartelera por fecha |
| GET | `/games/teams` | 30 equipos con ELO actual |
| GET | `/games/{game_pk}` | Ficha completa |
| GET | `/games/{game_pk}/odds` | Historial de cuotas (line movement) |

## Predicciones

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/predictions/daily?market=&day=` | Pool completo del día |
| GET | `/predictions/top/{board}` | Tableros: `moneyline`, `run-line`, `over`, `under`, `hits` (top 20), `home-runs`, `rbi`, `strikeouts`, `total-bases`, `stolen-bases`, `first-inning`, `value-bets`, `upsets` |
| GET | `/predictions/game/{game_pk}` | Todas las predicciones de un juego |
| GET | `/predictions/player/{mlb_id}` | Props del día de un jugador |

Cada predicción incluye: probabilidad, cuota justa, cuota de casa (si hay),
EV, edge, stake Kelly, confianza, riesgo, explicación en lenguaje natural y el
desglose de voto por modelo.

## Parlays

| GET | `/parlays/daily` | Los 6 perfiles del día |
| GET | `/parlays/profile/{profile}` | `conservative`, `balanced`, `aggressive`, `same_game`, `high_odds`, `ai_premium` |

## Jugadores, motor y bankroll

| GET | `/players/search?q=` · `/players/{mlb_id}/stats` |
| GET | `/stats/engine?days=&market=` — histórico win rate / ROI / Brier |
| GET | `/stats/weights?market=` — pesos vigentes del ensemble |
| GET/POST | `/bankroll`, `/bankroll/bets`, `/bankroll/bets/{id}/settle/{result}` |

## Admin (rol `admin`)

`/admin/users` (GET/PATCH) · `/admin/subscriptions` · `/admin/payments` ·
`/admin/logs` · `/admin/models` · `/admin/sources` · `/admin/overview` ·
`POST /admin/jobs/{bootstrap|refresh|predict|parlays|close-day}`

## Límites

120 req/min por IP (Redis, ventana deslizante) + 30 req/s con burst en NGINX.
Respuesta `429` con `Retry-After`.
