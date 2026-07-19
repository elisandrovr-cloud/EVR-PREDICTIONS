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
