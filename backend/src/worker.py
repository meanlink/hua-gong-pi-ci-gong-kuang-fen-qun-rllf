import time, logging
from pathlib import Path
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Report, Computation
from sqlalchemy import select
from src.services.business import analyze
from src.services import computations
from src.services.reports import deliver
from src.services.audit import record
logging.basicConfig(level=logging.INFO)


def execute(computation_id):
    with Session() as db:
        computation = db.get(Computation, computation_id)
        if not computation or computation.status not in ('queued', 'running'):
            return
        computations.run_computation(db, computation_id, analyze)
        computation = db.get(Computation, computation_id)
        if computation.status == 'completed':
            record(db, 'worker', 'computation.completed',
                   {'id': computation.id, 'epoch': computation.epoch})
        elif computation.status == 'failed':
            record(db, 'worker', 'computation.failed',
                   {'id': computation.id, 'error': computation.error})
        else:
            record(db, 'worker', 'computation.canceled',
                   {'id': computation.id, 'error': computation.error})
        db.commit()


def tick():
    with Session() as db:
        # SQL 排队兜底：Redis 不可用时仍能推进仍有有效等待者的计算
        for computation_id in computations.pending_computation_ids(db):
            execute(computation_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled == True, Report.next_run <= time.time())):
            d = deliver(db, r)
            if d:
                record(db, 'worker', 'report.delivered', {'id': r.id, 'delivery': d.id})
        db.commit()


def main():
    r = Redis.from_url(REDIS_URL, socket_timeout=3)
    # 单 worker 栈；崩溃不得遗留 running 计算，恢复后补齐仍有效的等待分析
    with Session() as db:
        recovered = computations.recover(db)
        for cid in recovered:
            record(db, 'worker', 'computation.recovered', {'id': cid})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item = r.blpop('computation:queue', timeout=1)
            if item:
                execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry')
            time.sleep(2)


if __name__ == '__main__':
    main()
