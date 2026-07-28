# Sistema Multi-Agente — EVR MLB AI ULTRA

Un **Supervisor AI** coordina ocho agentes especializados. Cada agente es dueño de
un dominio, corre en el ciclo de monitoreo y también responde preguntas que el
Supervisor le enruta desde el chat.

```
                      ┌──────────────────────────┐
                      │      SUPERVISOR AI       │
                      │  · reparte el trabajo    │
                      │  · aísla fallos          │
                      │  · sintetiza conclusión  │
                      └───────────┬──────────────┘
        ┌───────────────┬─────────┼─────────┬───────────────┐
        ▼               ▼         ▼         ▼               ▼
   1 Roster        2 Lineup   3 Player  4 Pitcher      5 Batter
   Intelligence    Intelligence Intelligence Intelligence Intelligence
        │               │         │         │               │
        └───────────────┴────┬────┴─────────┴───────────────┘
                             ▼
                    8 Prediction AI  (ensemble ML)
                             ▼
                    6 Betting Intelligence  (EV / edge / CLV)
                             ▼
                    7 News Intelligence  (publica el feed)
```

## Orden de ejecución (y por qué)

El ciclo respeta las dependencias de datos: primero se **recolecta** (rosters,
alineaciones), luego se **perfila** (jugadores), después se **analiza**
(lanzadores, bateadores), con eso se **predice** (ensemble), sobre las
predicciones se **valora** contra el libro, y al final se **publica** la noticia.

## Los ocho agentes

| # | Agente | Qué hace | Fuente oficial |
|---|--------|----------|----------------|
| 1 | **Roster Intelligence** | Diferencia el roster activo contra lo guardado y lee el cable oficial de transacciones: lesiones, activaciones, bajadas a ligas menores, suspensiones, altas y bajas. Cada hallazgo va al historial. | `/teams/{id}/roster`, `/transactions` |
| 2 | **Lineup Intelligence** | Espera la alineación oficial y la compara con la esperada: quién falta, quién cambió de turno al bate y si cambió el abridor. | `/schedule?hydrate=lineups,probablePitcher` |
| 3 | **Player Intelligence** | Construye la base de jugadores: bio, foto oficial, posición, mano, edad y estado de roster. | `/people` + CDN de fotos |
| 4 | **Pitcher Intelligence** | Sincroniza ERA, FIP, WHIP, K/9, BB/9, H/9, carga de trabajo y bullpen. | `/people/{id}/stats`, `/teams/{id}/stats` |
| 5 | **Batter Intelligence** | Sincroniza tasas por turno (hit, HR, BB, K, RBI) y la forma de los últimos 5 juegos. | `/people/{id}/stats?stats=gameLog` |
| 6 | **Betting Intelligence** | Compara probabilidad del modelo vs. probabilidad implícita de la cuota: EV, edge, Kelly, CLV y riesgo. | capa de sportsbook (ver abajo) |
| 7 | **News Intelligence** | Convierte los cambios detectados en un feed legible de noticias y lesiones, sin duplicados. | derivado de 1 y 2 |
| 8 | **Prediction AI** | Ejecuta el ensemble (RF, XGBoost, LightGBM, CatBoost, red neuronal, SGD online, stacking, ELO, Monte Carlo con actualización bayesiana) y arma parlays. | datos de los agentes 1–5 |

## Contrato de un agente

```python
class BaseAgent:
    name, title, description, specialties

    def work(db, registry, day) -> AgentReport      # ciclo de monitoreo
    def insight(db, query) -> AgentInsight | None   # aporte al chat
    def execute(...)                                # envuelve work(): mide,
                                                    # aísla el error y persiste
```

`execute()` garantiza que **un agente que falla nunca detiene a los demás**: el
error se captura, se registra con estado `error` en `agent_runs` y el ciclo sigue.

Cada agente además está **acotado por tiempo** (`AGENT_CYCLE_SECONDS`): procesa lo
que cabe en su presupuesto y continúa en el siguiente minuto. Por eso el ciclo
completo cabe dentro del límite de una función serverless.

## Ciclo de monitoreo (cada minuto)

| Entorno | Mecanismo |
|---|---|
| Docker / contenedores | Celery beat → `app.workers.tasks.run_agent_cycle` cada `AGENT_MONITOR_INTERVAL` (60 s) |
| Vercel / serverless | Vercel Cron → `GET /api/v1/cron/agents` cada minuto (protegido por `CRON_SECRET`) |
| Sin cron disponible | El auto-seed alterna fases en cada carga: backfill de estadísticas ↔ pase ligero de agentes |
| Manual | Botón **ACTUALIZAR AHORA** → `POST /api/v1/agents/refresh` (ciclo completo síncrono) |

El resultado del último ciclo se cachea en Redis y se expone en
`GET /api/v1/agents/last-cycle`, que alimenta la marca de "última actualización"
del dashboard.

## Historial de cambios

Todo movimiento se guarda en `roster_changes` con tipo, severidad, valor previo,
valor nuevo, quién lo detectó y la marca de tiempo:

```
change_type: injury | activated | optioned | suspended | added | removed |
             status_change | lineup_posted | lineup_absence | lineup_order |
             pitcher_change
severity:    info | warning | critical
```

Un cambio `critical` (lesión, suspensión, cambio de abridor) es la señal para
recalcular ese juego de inmediato.

## Chat: cómo se sintetiza una respuesta

1. **Parseo** — el Supervisor clasifica la intención (`hits`, `strikeouts`,
   `parlay`, `moneyline`, `value`, `news`, `lineup`, `player`…) y extrae el número
   de selecciones si lo pediste ("parlay de 10 picks" → 10). También detecta
   nombres de jugadores contra la base.
2. **Fan-out** — pregunta a **todos** los agentes; cada uno devuelve un
   `AgentInsight` si el tema es suyo, o `None` si no lo es.
3. **Síntesis** — el Supervisor compone **una** respuesta con:
   - apertura que dice qué revisó,
   - la sección de cada agente con sus datos,
   - **qué aumenta el riesgo** (lesiones críticas, ausencias, correlación en parlays),
   - conclusión con **nivel de confianza**,
   - y el aviso de que son estimaciones, no garantías.

Nunca responde con una lista pelada: cada selección lleva la estadística que la
respalda y el porqué.

> **Sin dependencia de un LLM externo.** El razonamiento es determinista y
> auditable sobre datos oficiales, así que funciona sin API keys y siempre da la
> misma respuesta para los mismos datos. La capa está aislada, de modo que se
> puede añadir un narrador LLM encima sin tocar la lógica de los agentes.

## Capa de sportsbook (Hard Rock Bet)

Hard Rock Bet **no publica una API de cuotas pública**, y raspar su sitio violaría
sus términos. La plataforma resuelve esto con un puerto intercambiable
(`infrastructure/providers/sportsbook.py`) con tres adaptadores:

| Adaptador | Estado | Cómo funciona |
|---|---|---|
| `ManualSportsbookProvider` | **activo por defecto** | Tú ingresas la línea que ves en tu cuenta (`POST /api/v1/odds/manual`) y el agente mide el edge contra ese precio exacto. |
| `OddsApiSportsbookProvider` | con `ODDS_API_KEY` | Agregador autorizado que redistribuye cuotas bajo licencia. |
| `AuthorizedFeedProvider` | placeholder | Para un feed licenciado/afiliado: pones `SPORTSBOOK_FEED_URL` + `SPORTSBOOK_FEED_KEY`, implementas `fetch_lines()` y nada más cambia. |

Ningún llamador sabe de dónde vino el precio, así que sustituir la fuente es un
cambio de una línea.

## Endpoints

```
GET  /api/v1/agents/status        estado del último run de cada agente
GET  /api/v1/agents/roster        el equipo de agentes y sus especialidades
GET  /api/v1/agents/last-cycle    último ciclo + marca de tiempo
POST /api/v1/agents/refresh       ACTUALIZAR AHORA (ciclo completo síncrono)
GET  /api/v1/agents/changes       historial de movimientos (filtros: severity, change_type)
GET  /api/v1/agents/news          feed de noticias y lesiones
POST /api/v1/agents/chat          preguntar al Supervisor
GET  /api/v1/agents/chat/history  transcripción

GET  /api/v1/players              directorio (kind=batters|pitchers|all, q, sort, order, paginación)
GET  /api/v1/players/{id}/profile perfil completo (bio, stats, últimos 5, props, noticias, cambios)
GET  /api/v1/players/compare?ids= comparación lado a lado (2–4 jugadores)

GET  /api/v1/odds/books           proveedores de cuotas disponibles
POST /api/v1/odds/manual          cargar una cuota vista en tu libro
GET  /api/v1/cron/agents          ciclo por HTTP (para Vercel Cron)
```

## Aviso

Toda recomendación es una **estimación estadística con nivel de confianza**, no
una garantía de resultado. La plataforma lo dice explícitamente en cada respuesta
del chat y en la documentación de la API.
