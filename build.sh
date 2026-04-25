#!/usr/bin/env bash
# Railway build script for InsightScribe backend

set -o errexit

# Ensure production settings are used in hosted deployments unless explicitly overridden.
export DJANGO_ENV="${DJANGO_ENV:-prod}"

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
