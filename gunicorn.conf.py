"""
gunicorn.conf.py — Configuration Gunicorn production (VPS Ubuntu)

Lancement :
  gunicorn -c gunicorn.conf.py app.main:app

NOTE : WORKERS=1 jusqu'au Jour 2 — le job store in-memory n'est pas
partageable entre plusieurs workers. Après intégration Redis (Jour 2),
passer à workers = multiprocessing.cpu_count() * 2 + 1.
"""
import multiprocessing
import os

# ─── Worker ──────────────────────────────────────────────────────────────────
# uvicorn.workers.UvicornWorker = FastAPI async natif
worker_class = "uvicorn.workers.UvicornWorker"

# TODO Jour 2 : décommenter après Redis
# workers = multiprocessing.cpu_count() * 2 + 1
workers = int(os.getenv("WORKERS", "1"))

worker_connections = 1000
max_requests = 1000          # Redémarre un worker après 1000 requêtes (memory leak protection)
max_requests_jitter = 100    # Évite le redémarrage simultané de tous les workers

# ─── Binding ─────────────────────────────────────────────────────────────────
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind = f"{host}:{port}"

# ─── Timeouts ────────────────────────────────────────────────────────────────
# CRITIQUE : le pipeline peut durer 30-60 min (Kling x18 clips).
# Le timeout Gunicorn doit être > durée max d'un pipeline.
# Les tâches longues tournent en background (BackgroundTasks FastAPI),
# donc la réponse HTTP est immédiate (202 Accepted) — timeout court suffit.
timeout = 120          # Timeout worker (requêtes HTTP, pas les background tasks)
graceful_timeout = 30  # Délai d'arrêt propre

# ─── Logs ────────────────────────────────────────────────────────────────────
accesslog = "-"     # stdout (capturé par systemd / journalctl)
errorlog = "-"      # stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ─── Sécurité ────────────────────────────────────────────────────────────────
# Limiter l'exposition — n8n sur le même VPS donc localhost seulement
# En production, nginx reverse proxy devant gunicorn
forwarded_allow_ips = "127.0.0.1"
proxy_protocol = False
