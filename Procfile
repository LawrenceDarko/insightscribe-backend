web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 120
worker: celery -A config.celery worker --loglevel=info --concurrency=4
