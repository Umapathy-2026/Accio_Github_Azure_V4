# gunicorn.conf.py
# SQLite-safe configuration: single worker, multi-threaded
# Switch to multiple workers after migrating to Azure SQL

bind = "0.0.0.0:8000"
workers = 1          # MUST stay 1 with SQLite. Increase to 2-4 after Azure SQL migration.
threads = 4          # Handles concurrent requests safely within one process
worker_class = "sync"
timeout = 120
keepalive = 5
max_requests = 1000  # Restart worker after 1000 requests to prevent memory leaks
max_requests_jitter = 100
preload_app = True
accesslog = "-"      # Log to stdout (Azure App Service captures this)
errorlog  = "-"
loglevel  = "info"