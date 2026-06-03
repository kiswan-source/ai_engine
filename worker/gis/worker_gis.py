"""GIS RQ Worker runner — python -m worker.gis.worker_gis"""
import redis
from rq import Worker
from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)

def main():
    conn = redis.from_url(settings.REDIS_URL)
    queues = [settings.RQ_QUEUE_GIS]
    logger.info("GIS Worker starting", queues=queues)
    Worker(queues=queues, connection=conn).work(with_scheduler=True)

if __name__ == "__main__":
    main()
