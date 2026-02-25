"""
InsightScribe - Common Permissions
"""

from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Object-level permission: only allow the owner of an object to access it.
    Expects the object to have a `user` or `owner` attribute.
    """

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        return owner == request.user
