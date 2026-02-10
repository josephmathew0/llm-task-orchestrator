# backend/app/worker.py

from redis import Redis
from rq import Queue
from app.settings import settings

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("tasks", connection=redis_conn)
