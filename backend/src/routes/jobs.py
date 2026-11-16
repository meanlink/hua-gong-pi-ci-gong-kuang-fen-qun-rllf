from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Job, Computation
from src.schemas.job import JobInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import jobs
from src.services.audit import record
from src.utils.serialization import job_dict, computation_dict
router = APIRouter(prefix='/jobs')


@router.get('')
def listing(db=Depends(get_db), u=Depends(current_user)):
    return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(100))]


@router.post('', status_code=201)
def create(data: JobInput, db=Depends(get_db), u=Depends(can_write)):
    j, started = jobs.create(db, data, u)
    record(db, u.email, 'job.create', {'id': j.id, 'params': j.params,
                                       'computation_id': j.computation_id,
                                       'reused_from_job_id': j.reused_from_job_id,
                                       'request_key': j.request_key})
    db.commit()
    # 仅当本请求实际启动了一份新的共享计算时才入队；复用成功结果不入队
    if started and j.computation_id and j.status == 'queued':
        jobs.enqueue(j.computation_id)
    return job_dict(j)


@router.get('/computations')
def computations(db=Depends(get_db), u=Depends(current_user)):
    rows = db.scalars(select(Computation).order_by(Computation.id.desc()).limit(100)).all()
    waiting = {}
    for c in rows:
        waiting[c.id] = db.scalars(
            select(Job).where(Job.computation_id == c.id).order_by(Job.id.asc())
        ).all()
    return [computation_dict(c, waiting.get(c.id, [])) for c in rows]


@router.get('/{id}')
def detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    j = jobs.get_or_404(db, id)
    return job_dict(j)


@router.post('/{id}/cancel')
def cancel(id: int, db=Depends(get_db), u=Depends(can_write)):
    j = jobs.get_or_404(db, id)
    before = j.computation_id
    j = jobs.cancel(db, j, u)
    record(db, u.email, 'job.cancel', {'id': id, 'computation_id': before, 'canceled': j.canceled})
    db.commit()
    return job_dict(j)


@router.post('/{id}/approve')
def approve(id: int, db=Depends(get_db), u=Depends(admin_only)):
    j = jobs.get_or_404(db, id)
    if j.status != 'completed':
        raise HTTPException(409, '仅已完成结果可以批准')
    j.approved = True
    record(db, u.email, 'job.approve', {'id': id})
    db.commit()
    return job_dict(j)
