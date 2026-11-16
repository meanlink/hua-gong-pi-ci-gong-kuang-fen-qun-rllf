"""共享计算：内容相同（与行序无关）、参数一致的分析共用同一份 KMeans 计算。

关键约定：
- 复用键 = 数据内容指纹（行序无关）+ 规范化参数指纹；分析名称不参与。
- 每个指纹在 computation_slots 中至多一条活动槽，行锁串行化创建，保证并发只启一份计算。
- 成功结果可被后续同指纹分析直接复用；失败不写槽、不缓存，再次创建会另开新计算。
- 同一指纹每次新开计算 epoch 递增；worker 完成时按 epoch 校验，旧执行迟到结果不得污染新计算。
- 全部等待者撤销才释放槽并停止共享计算；单个撤销不影响其他等待者。
"""
import json
import time
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Dataset, Job, Computation, ComputationSlot
from src.utils.serialization import computation_fingerprint


def _fingerprint(db, dataset, params):
    d = db.get(Dataset, dataset.id)
    return computation_fingerprint(d.records, params)


def _slot(db, fingerprint):
    return db.scalar(select(ComputationSlot).where(ComputationSlot.fingerprint == fingerprint))


def _find_reusable(db, fingerprint):
    """已成功的同指纹计算可直接复用；失败与进行中的计算不返回。"""
    return db.scalar(
        select(Computation)
        .where(Computation.fingerprint == fingerprint, Computation.status == 'completed')
        .order_by(Computation.id.desc())
    )


def create_job(db, data, user, params):
    """创建分析（参数已由调用方校验规范化）。同一 request_key 重试返回原任务，不新增分析。"""
    dataset = db.get(Dataset, data.dataset_id)
    if not dataset:
        raise HTTPException(404, '数据批次不存在')
    request_key = (data.request_key or '').strip() or None
    if request_key:
        existing = db.scalar(select(Job).where(Job.request_key == request_key))
        if existing:
            # 创建请求重试：原样返回既有分析（含已撤销项，撤销保持撤销）
            return existing, False
    fingerprint = _fingerprint(db, dataset, params)
    now = time.time()

    reusable = _find_reusable(db, fingerprint)
    if reusable:
        # 已有成功结果：直接复用，不启动任何计算
        source_job = db.scalar(
            select(Job)
            .where(Job.computation_id == reusable.id, Job.status == 'completed')
            .order_by(Job.id.asc())
        )
        job = Job(
            name=data.name, dataset_id=dataset.id, params=params, created_by=user.id,
            created_at=now, status='completed', result=reusable.result,
            finished_at=now, computation_id=reusable.id, request_key=request_key,
            reused_from_job_id=source_job.id if source_job else None,
        )
        db.add(job)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if request_key:
                again = db.scalar(select(Job).where(Job.request_key == request_key))
                if again:
                    return again, False
            raise
        # 直接复用成功结果：无需入队任何计算
        return job, False

    # 无成功结果：在活动槽上行锁，保证并发创建只启动一份计算
    enqueue = False
    slot = db.scalar(select(ComputationSlot).where(ComputationSlot.fingerprint == fingerprint).with_for_update())
    if slot is None:
        slot = ComputationSlot(fingerprint=fingerprint, computation_id=0, epoch=0, created_at=now)
        db.add(slot)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            slot = db.scalar(select(ComputationSlot).where(ComputationSlot.fingerprint == fingerprint))
    computation = db.get(Computation, slot.computation_id) if slot.computation_id else None
    if computation is None or computation.status not in ('queued', 'running'):
        # 新的共享计算：epoch 在该指纹全部历史代次上递增，
        # 即使槽曾因全撤销被释放，旧执行迟到结果也无法污染新计算
        max_epoch = db.scalar(
            select(Computation.epoch).where(Computation.fingerprint == fingerprint).order_by(Computation.epoch.desc()).limit(1)
        ) or 0
        epoch = max(slot.epoch or 0, max_epoch) + 1
        computation = Computation(
            fingerprint=fingerprint, dataset_id=dataset.id, params=params,
            epoch=epoch, status='queued', created_at=now,
        )
        db.add(computation)
        db.flush()
        slot.computation_id = computation.id
        slot.epoch = epoch
        slot.created_at = now
        enqueue = True

    job = Job(
        name=data.name, dataset_id=dataset.id, params=params, created_by=user.id,
        created_at=now, status='queued', computation_id=computation.id,
        request_key=request_key,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if request_key:
            again = db.scalar(select(Job).where(Job.request_key == request_key))
            if again:
                return again, False
        raise
    # 仅当本请求实际开启了一份新的共享计算时返回 True，由路由负责入队
    return job, enqueue


def cancel_job(db, job, user):
    """撤销一份等待分析。仅排队中的分析可撤销；全部等待者撤销才停止共享计算。"""
    if job.status not in ('queued', 'running') or job.canceled:
        if job.canceled:
            return job
        raise HTTPException(409, '仅等待中的分析可以撤销')
    job.canceled = True
    job.status = 'canceled'
    job.finished_at = time.time()
    computation = db.get(Computation, job.computation_id) if job.computation_id else None
    if computation and computation.status in ('queued', 'running'):
        others = db.scalar(
            select(Job.id)
            .where(Job.computation_id == computation.id, Job.canceled == False)  # noqa: E712
            .limit(1)
        )
        if others is None:
            # 全部撤销：停止共享计算并释放槽，此后新建分析另开计算
            computation.status = 'canceled'
            computation.finished_at = time.time()
            slot = _slot(db, computation.fingerprint)
            if slot and slot.computation_id == computation.id:
                db.delete(slot)
    return job


def _active_waiters(db, computation):
    return list(db.scalars(
        select(Job)
        .where(Job.computation_id == computation.id, Job.canceled == False)  # noqa: E712
        .order_by(Job.id.asc())
    ))


def complete_computation(db, computation, result):
    """计算成功：把结果分发给所有仍有效（未撤销）的等待分析；已撤销者保持撤销。"""
    now = time.time()
    computation.status = 'completed'
    computation.result = result
    computation.error = ''
    computation.finished_at = now
    slot = _slot(db, computation.fingerprint)
    if slot and slot.computation_id == computation.id:
        db.delete(slot)
    first = None
    for job in _active_waiters(db, computation):
        job.status = 'completed'
        job.result = result
        job.finished_at = now
        if first is None:
            first = job
        else:
            job.reused_from_job_id = first.id
    return first


def fail_computation(db, computation, error):
    """计算失败：失败结果不作缓存（释放槽），等待分析各自保留失败原因。"""
    now = time.time()
    computation.status = 'failed'
    computation.error = error[:990]
    computation.finished_at = now
    slot = _slot(db, computation.fingerprint)
    if slot and slot.computation_id == computation.id:
        db.delete(slot)
    for job in _active_waiters(db, computation):
        job.status = 'failed'
        job.error = error[:990]
        job.finished_at = now


def abort_computation(db, computation, reason):
    """worker 发现计算已被全部撤销或代次失效：不产出结果、不污染任何分析。"""
    computation.status = 'canceled'
    computation.error = reason[:990]
    computation.finished_at = time.time()
    slot = _slot(db, computation.fingerprint)
    if slot and slot.computation_id == computation.id:
        db.delete(slot)


def run_computation(db, computation_id, runner):
    """worker 执行入口，含存活检查与 epoch 隔离；runner(records, params) 返回真实结果。"""
    computation = db.get(Computation, computation_id)
    if not computation or computation.status not in ('queued', 'running'):
        return
    # 全部等待者已撤销：停止这份共享计算，不浪费算力
    if not _active_waiters(db, computation):
        abort_computation(db, computation, '全部等待分析已撤销，停止共享计算')
        db.commit()
        return
    computation.status = 'running'
    computation.started_at = time.time()
    db.commit()
    try:
        dataset = db.get(Dataset, computation.dataset_id)
        result = runner(dataset.records, computation.params)
        json.dumps(result, allow_nan=False)
    except Exception as exc:  # 业务/算法失败
        logging.exception('Shared computation failed')
        fail_computation(db, computation, str(exc))
        db.commit()
        return
    # 提交前再次确认仍是当前活动代次，旧执行迟到结果不得污染新计算
    slot = _slot(db, computation.fingerprint)
    if slot is None or slot.computation_id != computation.id or slot.epoch != computation.epoch:
        abort_computation(db, computation, '计算代次已失效，迟到结果不予采用')
        db.commit()
        return
    if not _active_waiters(db, computation):
        abort_computation(db, computation, '全部等待分析已撤销，停止共享计算')
        db.commit()
        return
    complete_computation(db, computation, result)
    db.commit()


def recover(db):
    """worker 启动与周期兜底：崩溃中断后把未完成计算重新排队，恢复后补齐有效分析。"""
    now = time.time()
    stale = list(db.scalars(select(Computation).where(Computation.status == 'running')))
    for computation in stale:
        if not _active_waiters(db, computation):
            abort_computation(db, computation, 'worker 中断恢复：已无有效等待分析')
            continue
        computation.status = 'queued'
        computation.started_at = None
        slot = _slot(db, computation.fingerprint)
        if slot is None:
            slot = ComputationSlot(
                fingerprint=computation.fingerprint, computation_id=computation.id,
                epoch=computation.epoch, created_at=now,
            )
            db.add(slot)
        elif slot.computation_id != computation.id:
            slot.computation_id = computation.id
            slot.epoch = computation.epoch
            slot.created_at = now
    # 孤儿槽（指向已终结计算）清理，保证此后新建分析可另开计算
    for slot in list(db.scalars(select(ComputationSlot))):
        computation = db.get(Computation, slot.computation_id)
        if not computation or computation.status not in ('queued', 'running'):
            db.delete(slot)
    # 计算已成功但个别分析尚未拿到结果（提交中断）：补齐仍有效的分析
    for computation in db.scalars(select(Computation).where(Computation.status == 'completed')):
        if not computation.result:
            continue
        pending = list(db.scalars(
            select(Job).where(
                Job.computation_id == computation.id,
                Job.canceled == False,  # noqa: E712
                Job.status != 'completed',
            )
        ))
        if pending:
            first = db.scalar(
                select(Job)
                .where(Job.computation_id == computation.id, Job.status == 'completed')
                .order_by(Job.id.asc())
            )
            for job in pending:
                job.status = 'completed'
                job.result = computation.result
                job.finished_at = now
                job.error = ''
                if first:
                    job.reused_from_job_id = first.id
    db.commit()
    return [c.id for c in stale if c.status == 'queued']


def pending_computation_ids(db, limit=3):
    """SQL 排队兜底：取出仍有有效等待者的排队计算。"""
    ids = []
    for computation in db.scalars(
        select(Computation).where(Computation.status == 'queued').order_by(Computation.id.asc()).limit(limit * 2)
    ):
        if _active_waiters(db, computation):
            ids.append(computation.id)
            if len(ids) >= limit:
                break
    return ids
