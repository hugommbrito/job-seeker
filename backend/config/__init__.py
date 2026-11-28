# Loaded with Django, so @shared_task binds to this project's Celery application.
from config.celery import app as celery_app

__all__ = ["celery_app"]
