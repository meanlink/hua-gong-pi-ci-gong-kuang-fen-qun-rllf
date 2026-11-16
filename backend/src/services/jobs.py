from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services import computations
from src.services.business import metadata


def normalize_params(data):
    allowed = {p['key']: p for p in metadata().get('parameters', [])}
    if set(data.params) - set(allowed):
        raise HTTPException(422, '包含未知分析参数')
    params = {k: p['default'] for k, p in allowed.items()}
    params.update(data.params)
    for key, p in allowed.items():
        v = params[key]
        if p['type'] == 'number':
            try:
                v = float(v)
                if not (p.get('min', -1e9) <= v <= p.get('max', 1e9)):
                    raise ValueError()
                params[key] = v
            except (ValueError, TypeError):
                raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options', [])]:
            raise HTTPException(422, f'{p["label"]} 不是有效选项')
    return params


def create(db, data, user):
    if not db.get(Dataset, data.dataset_id):
        raise HTTPException(404, '数据批次不存在')
    params = normalize_params(data)
    return computations.create_job(db, data, user, params)


def get_or_404(db, job_id):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, '分析任务不存在')
    return j


def cancel(db, job, user):
    if user.role != 'admin' and job.created_by != user.id:
        raise HTTPException(403, '只能撤销本人创建的等待分析')
    return computations.cancel_job(db, job, user)


def enqueue(computation_id):
    try:
        r = Redis.from_url(REDIS_URL)
        r.rpush('computation:queue', computation_id)
        r.close()
    except Exception:
        pass  # SQL queued status is the durable fallback
