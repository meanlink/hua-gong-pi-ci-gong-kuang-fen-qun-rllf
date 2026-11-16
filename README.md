# 化工批次工况分群

KMeans 聚类的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、字段验证、批次指纹）→ 参数化分析（异步 Python worker，共享计算去重）→ 结果复核（指标、图形、明细、解释、批准）→ 定时分发（本地收件箱、CSV/JSON、SHA256）；另有业务总览、共享计算视图和审计轨迹。
三个贯穿全栈的实体：Dataset 数据批次、Job 分析任务、Report 分发计划；辅助 User、Audit、Delivery、Computation/ComputationSlot 共享计算。

## 共享计算（同内容同参数只算一次）
- 复用键 = 数据内容指纹（逐行规范化后排序，**与行序无关**）+ 规范化分群参数指纹；分析名称不参与。
- 并发创建只启动一份计算：每个复用键在 `computation_slots` 持唯一活动槽（数据库行锁/唯一约束串行化），多个 Job 关联同一 `computations` 记录，各自保留独立名称、批准与分发。
- 已有成功结果时新建分析直接复用并标注 `reused_from_job_id`，不再入队；**失败结果不缓存**，再建即另开新计算。
- 撤销：单份等待分析撤销不影响其他等待者；全部撤销才停止共享计算并释放槽。撤销项保持撤销，不被后续补齐。
- 代次隔离：同一复用键每次新开计算 `epoch` 递增，worker 提交前校验活动槽代次，旧执行迟到结果一律拒绝，不污染新计算。
- 崩溃恢复：worker 启动把残留 running 计算重新排队；计算已成功但部分分析未拿到结果时（提交中断）恢复后补齐有效分析。
- 创建请求可带 `request_key`，网络重试同键返回原分析、不新增；页面在「共享计算」视图查询复用来源、等待关系与失败原因。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18209；后端文档 http://localhost:19209/docs；数据库宿主端口 17709。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载|
|analyst@demo.local|Demo123!|接入、执行、读取与下载；不能批准或安排分发|
|viewer@demo.local|Demo123!|只读与下载|

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；MySQL 8.0；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer；JobStatus：queued/running/completed/failed/canceled；ComputationStatus：queued/running/completed/failed/canceled。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=batch-clusters；FRONTEND_PORT=18209；BACKEND_PORT=19209；DB_PORT=17709；DB_PASSWORD、JWT_SECRET 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，数据库/Redis 各持久卷。
恰好五服务均有健康检查。Redis 队列（键 `computation:queue`）加 SQL 排队状态兜底；worker 按 next_run 生成本地收件箱文件。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。当前不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1010/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
