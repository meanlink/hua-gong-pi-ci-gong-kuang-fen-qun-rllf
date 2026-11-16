import hashlib, json


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def dataset_dict(d):
    return {'id': d.id, 'name': d.name, 'source': d.source, 'rows': len(d.records), 'checksum': d.checksum, 'created_at': d.created_at}


def _canonical(value):
    """规范化为可 JSON 序列化的稳定结构，数值统一为 float 保证 3 与 3.0 同指纹。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, dict):
        return {str(k): _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def content_fingerprint(records):
    """数据内容指纹：逐行规范化后排序，行序不同但内容相同的批次得到同一指纹。"""
    rows = [checksum(_canonical(row)) for row in records]
    rows.sort()
    return checksum(rows)


def params_fingerprint(params):
    """分群参数指纹：键排序、数值规范化，参数书写差异不影响复用。"""
    return checksum(_canonical(params))


def computation_fingerprint(records, params):
    return hashlib.sha256((content_fingerprint(records) + ':' + params_fingerprint(params)).encode()).hexdigest()


def job_dict(j):
    return {k: getattr(j, k) for k in ['id', 'name', 'dataset_id', 'params', 'status', 'result', 'error', 'approved', 'created_at', 'finished_at', 'request_key', 'computation_id', 'reused_from_job_id', 'canceled']}


def computation_dict(c, waiting_jobs=None):
    data = {k: getattr(c, k) for k in ['id', 'fingerprint', 'dataset_id', 'params', 'epoch', 'status', 'error', 'created_at', 'started_at', 'finished_at']}
    if waiting_jobs is not None:
        data['waiting_jobs'] = [
            {'id': j.id, 'name': j.name, 'status': j.status, 'canceled': j.canceled,
             'reused_from_job_id': j.reused_from_job_id}
            for j in waiting_jobs
        ]
    return data


def report_dict(r):
    return {k: getattr(r, k) for k in ['id', 'name', 'job_id', 'destination', 'interval_seconds', 'next_run', 'enabled']}


def delivery_dict(d):
    return {k: getattr(d, k) for k in ['id', 'report_id', 'created_at', 'checksum', 'filename', 'destination']}
