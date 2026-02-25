import os

environment = os.environ.get("DJANGO_ENV", "dev")

if environment == "prod":
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
