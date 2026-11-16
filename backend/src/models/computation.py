from sqlalchemy import String, JSON, Double, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Computation(Base):
    """一次真实的聚类计算。内容相同（与行序无关）且分群参数一致的多个分析共享同一计算。"""
    __tablename__ = 'computations'
    id: Mapped[int] = mapped_column(primary_key=True)
    # 复用键：数据内容指纹 + 规范化参数指纹；与批次行序、分析名称无关
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # 同一 fingerprint 的计算代次：全撤销后再建会递增，旧执行迟到结果按代次隔离
    epoch: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    created_at: Mapped[float] = mapped_column(Double)
    started_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)


class ComputationSlot(Base):
    """每个 fingerprint 至多一条活动槽。存在即代表当前有一份进行中的共享计算。"""
    __tablename__ = 'computation_slots'
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    computation_id: Mapped[int] = mapped_column(Integer)
    epoch: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Double)
