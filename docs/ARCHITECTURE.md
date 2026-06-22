# 架构

系统采用模块化单体：React/Ant Design 前端由 Nginx 托管；FastAPI 提供 API；SQLAlchemy/Alembic 管理 PostgreSQL/PostGIS。业务服务依赖 `DataProvider`、`ScoringEngine`、`ReportRenderer` 抽象，M1 分别实现高德、规则评分和标准报告。外部数据保留原始 JSON、采集时间和置信度。Nginx 是唯一公开端口，数据库不映射宿主端口。
