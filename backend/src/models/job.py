from sqlalchemy import String, JSON, Double, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # 客户端创建请求键：同一请求重试不新增分析
    request_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    # 所属共享计算；历史直接完成的任务允许为空，保持历史分析可读
    computation_id: Mapped[int | None] = mapped_column(ForeignKey('computations.id'), nullable=True)
    # 结果复用来源：本分析直接复用了哪个已成功分析的结果
    reused_from_job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    # 撤销的等待分析保持撤销，不再被后续计算补齐
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)
