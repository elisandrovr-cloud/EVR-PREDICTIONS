# EVR MLB AI ULTRA

Plataforma autónoma de análisis y apuestas de MLB: un **equipo de 8 agentes de IA
coordinados por un Supervisor** trabaja las 24 horas para que tú no tengas que
investigar nada. Entras, y las mejores oportunidades ya están analizadas,
priorizadas y explicadas.

- **Sistema multi-agente** — rosters, alineaciones, jugadores, lanzadores,
  bateadores, cuotas, noticias y predicción, cada uno con su especialista.
  Monitoreo **cada minuto** con historial de cambios. → [`docs/MULTI_AGENT.md`](docs/MULTI_AGENT.md)
- **Chat IA** — «dame un parlay de 10 picks», «los mejores hits», «¿qué jugador
  tiene más valor hoy?». El Supervisor consulta a todos los agentes y responde
  **justificando cada selección** con las estadísticas que la respaldan.
- **Base de datos de jugadores** — bateadores y lanzadores separados, con perfil
  individual (bio, foto oficial, splits, forma de los últimos 5 juegos, noticias)
  búsqueda, orden y comparación.
- **EVR Prediction Engine** — ensemble que se recalibra solo cada noche contra
  los resultados oficiales, sin intervención humana.

```
┌─────────────┐   ┌──────────────┐   ┌────────────────────────────┐
│   NGINX     │──▶│  Next.js 15  │   │  Celery beat + workers     │
│ (edge, RL)  │   │  (terminal)  │   │  · agentes cada 1 min      │
│             │──▶│  FastAPI     │◀─▶│  · refresh cada 2 min      │
└─────────────┘   │  (REST+JWT)  │   │  · cierre nocturno (IA)    │
                  └──────┬───────┘   └──────────┬─────────────────┘
                         │                      │
                  ┌──────▼──────┐        ┌──────▼──────┐
                  │ PostgreSQL  │        │    Redis    │
                  └─────────────┘        └─────────────┘

   SUPERVISOR AI ──▶ 1 Roster · 2 Lineup · 3 Player · 4 Pitcher
                     5 Batter · 6 Betting · 7 News · 8 Prediction
```

## Arranque con un solo comando

```bash
cp .env.example .env    # edita SECRET_KEY y las API keys opcionales
docker compose up
```

| Servicio | URL |
|---|---|
| Aplicación | http://localhost |
| API + Swagger | http://localhost/docs |
| ReDoc | http://localhost/redoc |

En el primer arranque el pipeline hace bootstrap automático (equipos, cartelera
del día, lineups, stats). Con `ODDS_API_KEY` y `OPENWEATHER_API_KEY`
configuradas se activan cuotas en vivo y clima por estadio; sin ellas la
plataforma funciona con probabilidades justas del modelo.

Para crear un admin:

```bash
docker compose exec backend python -c "
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models import User
db = SessionLocal()
u = db.query(User).filter_by(email='TU_EMAIL').one(); u.role='admin'; db.commit()"
```

## El motor de predicción

Ocho votantes por mercado, combinados en logit-space con pesos bayesianos:

| Modelo | Rol |
|---|---|
| Monte Carlo | Simulación inning-a-inning (parque, clima, umpire, bullpen) |
| ELO | Prior de fuerza de equipos con ventaja local y margen de victoria |
| Random Forest / XGBoost / LightGBM / CatBoost | Zoo entrenado con histórico features→resultado |
| Red neuronal (MLP) | Miembro no lineal del zoo |
| SGD online | Aprendizaje incremental diario (partial_fit) |
| Stacking (LogReg) | Meta-aprendiz sobre los votos del zoo |

**Ciclo de aprendizaje nocturno (sin intervención humana):** liquidar
predicciones contra boxscores oficiales → actualización multiplicativa de pesos
por log-loss (recuperable, nunca llegan a cero) → ELO con marcadores finales →
reentrenamiento del zoo → snapshot de métricas (win rate, Brier, ROI).

**Mercados cubiertos:** moneyline, run line, over/under, primera entrada, y
props de bateador (hits, HR, RBI, bases totales, robos, carreras, BB) y de
pitcher (K, BB, outs, hits permitidos, carreras limpias, victoria, quality
start, no-hitter). Parlays automáticos en 6 perfiles (conservador, balanceado,
agresivo, same-game, high-odds, AI premium) con haircut de correlación.

**Value bets:** EV y edge contra la mejor cuota capturada + stake sugerido por
Kelly fraccional (25%).

## Fuentes de datos

Activas sin configuración: **MLB Stats API** (calendario, lineups, pitchers,
umpires, boxscores, stats), **Baseball Savant** (xStats, calidad de contacto),
**FanGraphs** (leaderboards avanzados), factores de parque y tendencias de
umpires curados. Con API key: **The Odds API**, **OpenWeather**. Feeds
licenciados (Rotowire, Action Network, VSIN, sharp money…) están declarados como
adaptadores con la misma interfaz — conectar uno no toca el resto del código —
y reportan estado `disabled` hasta tener credenciales.

## Estructura

```
backend/
  app/domain/          # entidades y eventos (núcleo del hexágono)
  app/application/     # casos de uso: ingestión, predicción, parlays, resultados
  app/infrastructure/  # SQLAlchemy, Redis, proveedores HTTP
  app/ml/              # EVR Prediction Engine (ensemble completo)
  app/api/v1/          # REST (Swagger en /docs)
  app/workers/         # Celery: beat cada 2 min + eventos + cierre nocturno
  tests/               # 71 pruebas (pytest)
frontend/
  src/app/             # terminal, juegos, predicciones, parlays, jugadores,
                       # motor IA, bankroll, admin, login/registro
  src/components/      # UI estilo Bloomberg + gráficos Recharts
nginx/                 # edge: rate limit, security headers, proxy
.github/workflows/     # CI: tests backend, build frontend, imágenes Docker
docs/                  # arquitectura, API, despliegue AWS
```

## Seguridad

JWT con refresh-token rotativo (un solo uso), OAuth Google/GitHub, rate
limiting en dos capas (NGINX + ventana deslizante en Redis), cabeceras de
seguridad tipo Helmet, CORS restringido, log de auditoría de acciones sensibles
y logging JSON estructurado.

## Desarrollo

```bash
make test          # pruebas backend + typecheck frontend
make logs          # logs en vivo
make seed          # fuerza bootstrap de datos
docs/              # documentación extendida
```

## Otros proyectos en este repositorio

- [`EVR-Emulator/`](EVR-Emulator/README.md) — **EVR Emulator "Elisandro"**:
  entorno de virtualización Android (QEMU + BlissOS) con middleware Node.js
  (REST + WebSocket + ADB) y consola web con pantalla en vivo. Es un proyecto
  independiente del backend de MLB; se arranca desde su propia carpeta.

## Aviso

Esta plataforma es una herramienta de análisis estadístico. Ninguna probabilidad
garantiza resultados; apuesta de forma responsable y conforme a la legislación
de tu jurisdicción.
