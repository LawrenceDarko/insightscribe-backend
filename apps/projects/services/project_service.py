"""
InsightScribe - Project Services
"""

import logging

from apps.projects.models import Project

logger = logging.getLogger("apps.projects")


def create_project(user, name, description=""):
    """Create a new project for the given user."""
    project = Project.objects.create(user=user, name=name, description=description)
    logger.info("Project created: %s by %s", project.id, user.email)
    return project


def get_user_projects(user):
    """Return all active projects for a user."""
    return Project.objects.filter(user=user).select_related("user")


def get_project_for_user(project_id, user):
    """Retrieve a single project, ensuring ownership."""
    try:
        return Project.objects.select_related("user").get(id=project_id, user=user)
    except Project.DoesNotExist:
        return None


def update_project(project, **kwargs):
    """Update project fields."""
    for key, value in kwargs.items():
        if hasattr(project, key):
            setattr(project, key, value)
    project.save()
    logger.info("Project updated: %s", project.id)
    return project


def delete_project(project):
    """Soft-delete a project."""
    project.soft_delete()
    logger.info("Project soft-deleted: %s", project.id)
