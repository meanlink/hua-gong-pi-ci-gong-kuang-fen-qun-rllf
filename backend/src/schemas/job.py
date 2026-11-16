from pydantic import BaseModel, Field
class JobInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_id: int
    params: dict = Field(default_factory=dict)
    # 客户端请求键：网络重试时携带同一键，后端保证不新增分析
    request_key: str | None = Field(default=None, max_length=64)
