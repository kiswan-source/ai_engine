"""AI RQ Worker runner — start with: python -m worker.ai.worker_ai"""
import redis
from rq import Worker

from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    conn = redis.from_url(settings.REDIS_URL)
    queues = [settings.RQ_QUEUE_AI]
    logger.info("AI Worker starting", queues=queues)
    worker = Worker(queues=queues, connection=conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
