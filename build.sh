#!/usr/bin/env bash
# Railway build script for InsightScribe backend

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
