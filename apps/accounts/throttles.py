"""
InsightScribe - Authentication Throttles
Dedicated rate-limiting classes for auth endpoints.
Stricter than the global default to protect against brute-force attacks.
"""

from rest_framework.throttling import AnonRateThrottle


class AuthBurstThrottle(AnonRateThrottle):
    """
    Short burst limiter for auth endpoints (register/login/refresh).
    Prevents rapid-fire credential stuffing.
    """

    scope = "auth_burst"


class AuthSustainedThrottle(AnonRateThrottle):
    """
    Sustained rate limiter for auth endpoints.
    Protects against slower distributed brute-force attacks.
    """

    scope = "auth_sustained"
