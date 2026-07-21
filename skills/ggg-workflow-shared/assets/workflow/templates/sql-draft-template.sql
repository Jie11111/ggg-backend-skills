-- GGG_SQL_DRAFT_VERSION: 1
-- SQL影响类型: 查询或DML / DDL
-- 来源Cxx:
-- 说明:

-- 用途：在需求对齐阶段记录并让用户确认本次新增或修改的精确 SQL 语义。
-- 每条 SQL 前必须有且只有一条 GGG_SQL 元数据；id 与 01-research.md 的 SQL ID 一致。
-- type 仅允许 SELECT / INSERT / UPDATE / DELETE / DDL；objects、claims 必须为非空数组。
-- GGG_SQL: {"id":"SQL1","type":"SELECT","objects":["table_name"],"claims":["C1"]}

SELECT column_name
FROM table_name
WHERE condition = ?;
