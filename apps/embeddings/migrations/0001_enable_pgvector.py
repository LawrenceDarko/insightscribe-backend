"""
Initial migration to enable pgvector extension.
Run this BEFORE any model migrations.
"""

from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        CreateExtension("vector"),
    ]
