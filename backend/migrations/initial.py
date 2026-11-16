from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models

# 旧库升级时需要补齐的列（全新库由 create_all 直接建出）
_ADDED_COLUMNS = {
    'jobs': [
        ('request_key', 'VARCHAR(64) NULL'),
        ('computation_id', 'INTEGER NULL'),
        ('reused_from_job_id', 'INTEGER NULL'),
        ('canceled', 'BOOLEAN NOT NULL DEFAULT 0'),
    ],
}


def _ensure_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        # request_key 唯一索引：创建请求重试不新增分析
        if 'jobs' in existing_tables:
            indexes = {idx['name'] for idx in inspector.get_indexes('jobs')}
            uniques = {u['name'] for u in inspector.get_unique_constraints('jobs')}
            if 'uq_jobs_request_key' not in indexes and 'uq_jobs_request_key' not in uniques:
                conn.execute(text('CREATE UNIQUE INDEX uq_jobs_request_key ON jobs (request_key)'))


def migrate():
    Base.metadata.create_all(engine)
    _ensure_columns()


if __name__ == '__main__':
    migrate()
