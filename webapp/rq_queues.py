from rq import Queue
from redis import Redis

_DEFAULT_TIMEOUT = 60 * 60

redis_conn = Redis()
default_queue = Queue(connection=redis_conn, default_timeout=_DEFAULT_TIMEOUT)
retry_queue = Queue("retry", connection=redis_conn)
failed_queue = Queue("failed", connection=redis_conn)
