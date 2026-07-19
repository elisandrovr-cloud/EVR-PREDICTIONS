# Despliegue

## Local / VPS (Docker Compose)

```bash
cp .env.example .env
# obligatorio: SECRET_KEY aleatorio de 64 hex
# recomendado: ODDS_API_KEY, OPENWEATHER_API_KEY
docker compose up -d
```

TLS en producción: termina HTTPS delante de NGINX (Caddy, Traefik o un ALB) o
añade certificados al propio NGINX.

## AWS (arquitectura de referencia)

| Pieza | Servicio AWS |
|---|---|
| Contenedores (backend, worker, beat, frontend) | ECS Fargate (o EKS) |
| Base de datos | RDS PostgreSQL 16 (Multi-AZ) |
| Cache / broker | ElastiCache Redis 7 |
| Edge | ALB + CloudFront (estáticos del frontend) |
| Artefactos de modelos | EFS montado en tasks de worker, o S3 con sync al boot |
| Secretos | Secrets Manager → variables de entorno de las task definitions |
| Imágenes | ECR (push desde GitHub Actions) |
| Observabilidad | CloudWatch Logs (el backend ya emite JSON estructurado) |

Pasos:

1. Crear ECR y subir imágenes (`docker build` + `docker push`) — el workflow de
   CI ya valida que ambas imágenes construyen.
2. RDS + ElastiCache en subredes privadas; security groups solo desde ECS.
3. Task definitions: mismas variables que `.env.example`, con `DATABASE_URL` y
   `REDIS_URL` apuntando a los endpoints administrados.
4. Servicios ECS: `backend` (≥2 tasks tras ALB), `worker` (autoscaling por
   profundidad de cola), `beat` (exactamente 1 task), `frontend`.
5. Migraciones: `alembic upgrade head` como task one-off en cada deploy
   (el boot también hace `create_all`, idempotente, para el primer arranque).

## CI/CD

`.github/workflows/ci.yml` corre en cada push/PR: pruebas del backend con
cobertura, typecheck + build del frontend, validación del compose y build de
ambas imágenes. Para CD, añade un job que haga push a ECR y fuerce nuevo
deployment del servicio ECS cuando `main` pase verde.

## Operación

- **Backups**: snapshots automáticos de RDS; el volumen de modelos es
  reconstruible (se reentrena con el histórico de la base).
- **Zona horaria**: todo el pipeline corre en UTC; el cierre nocturno a las
  08:30 UTC cubre la costa oeste.
- **Claves**: rota `SECRET_KEY` solo con ventana de logout global asumida;
  los refresh tokens rotan solos en cada uso.
