import os

environment = os.environ.get("DJANGO_ENV")

# Default to production on Railway unless explicitly overridden.
if not environment:
    environment = "prod" if os.environ.get("RAILWAY_ENVIRONMENT") else "dev"

if environment == "prod":
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
