#!/usr/bin/env python3
"""轻量扫描仓库中的模块、入口和依赖信号，辅助技术方案设计。"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".gradle",
    ".mvn",
    "node_modules",
    "target",
    "build",
    "out",
    "ggg",
    "dist",
    ".vscode",
}

ROLE_SUFFIXES = {
    "Controller": "Controller.java",
    "Service": "Service.java",
    "ServiceImpl": "ServiceImpl.java",
    "Facade": "Facade.java",
    "Provider": "Provider.java",
    "Mapper": "Mapper.java",
    "Repository": "Repository.java",
    "Manager": "Manager.java",
    "Handler": "Handler.java",
    "Converter": "Converter.java",
    "DTO": "DTO.java",
    "VO": "VO.java",
}

SIGNAL_PATTERNS = {
    "@DubboReference": re.compile(r"@DubboReference\b|@Reference\b"),
    "@DubboService": re.compile(r"@DubboService\b"),
    "FeignClient": re.compile(r"@FeignClient\b"),
    "RestTemplate/WebClient": re.compile(r"\bRestTemplate\b|\bWebClient\b"),
    "MQ-Producer": re.compile(r"@RocketMQ|RocketMQTemplate|KafkaTemplate|RabbitTemplate|@SendTo\b"),
    "MQ-Consumer": re.compile(r"@RocketMQMessageListener|@KafkaListener|@RabbitListener|@StreamListener"),
    "@Scheduled": re.compile(r"@Scheduled\b"),
    "@XxlJob": re.compile(r"@XxlJob\b"),
    "@EventListener": re.compile(r"@EventListener\b|@TransactionalEventListener\b"),
    "Redis": re.compile(r"\bRedisTemplate\b|\bStringRedisTemplate\b|@Cacheable\b|@CacheEvict\b|@CachePut\b"),
    "ES": re.compile(r"\bElasticsearchRestTemplate\b|\bRestHighLevelClient\b|@Document\b"),
}

# 从 Java 源码中提取表名的模式
TABLE_NAME_PATTERNS = [
    re.compile(r'@TableName\s*\(\s*"([^"]+)"'),
    re.compile(r'@TableName\s*\(\s*value\s*=\s*"([^"]+)"'),
    re.compile(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"'),
    re.compile(r'@Entity.*\n.*@Table\s*\(\s*name\s*=\s*"([^"]+)"', re.MULTILINE),
]

# Spring Boot 配置文件中的关键配置项
CONFIG_KEY_PATTERNS = {
    "端口": re.compile(r"server\.port\s*[:=]\s*(\S+)"),
    "数据源URL": re.compile(r"(?:spring\.datasource|datasource).*url\s*[:=]\s*(\S+)"),
    "Redis": re.compile(r"spring\.(?:data\.)?redis\.host\s*[:=]\s*(\S+)"),
    "Dubbo应用名": re.compile(r"dubbo\.application\.name\s*[:=]\s*(\S+)"),
    "Dubbo注册中心": re.compile(r"dubbo\.registry\.address\s*[:=]\s*(\S+)"),
    "Nacos": re.compile(r"spring\.cloud\.nacos\.(?:discovery|config)\.server-addr\s*[:=]\s*(\S+)"),
    "MQ-NameServer": re.compile(r"rocketmq\.name-server\s*[:=]\s*(\S+)"),
}


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def detect_repo_root(feature_dir: Path) -> Path:
    current = feature_dir.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "ggg").exists():
            return parent
    raise FileNotFoundError("未找到仓库根目录")


def parse_pom(pom_path: Path) -> tuple[str, str]:
    try:
        root = ET.parse(pom_path).getroot()
    except ET.ParseError:
        return ("", "")
    artifact_id = ""
    packaging = ""
    for node in list(root):
        tag = node.tag.split("}", 1)[-1]
        if tag == "artifactId" and node.text:
            artifact_id = node.text.strip()
        elif tag == "packaging" and node.text:
            packaging = node.text.strip()
    return artifact_id, packaging or "jar"


def parse_gradle(gradle_path: Path) -> tuple[str, str]:
    """从 build.gradle / build.gradle.kts 中提取基本信息。"""
    try:
        text = gradle_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ("", "")
    # 尝试提取 group 和 archivesBaseName
    artifact = ""
    packaging = "jar"
    m = re.search(r"archivesBaseName\s*=\s*['\"]([^'\"]+)['\"]", text)
    if m:
        artifact = m.group(1)
    if "war" in text.lower() and ("apply plugin" in text or "id 'war'" in text or "id(\"war\")" in text):
        packaging = "war"
    return artifact or gradle_path.parent.name, packaging


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def locate_module(module_dirs: list[Path], file_path: Path) -> Path:
    candidates = [d for d in module_dirs if d == file_path.parent or d in file_path.parents]
    if not candidates:
        return file_path.parent
    return max(candidates, key=lambda item: len(item.parts))


def collect_modules(repo_root: Path) -> list[dict[str, str]]:
    modules: list[dict[str, str]] = []
    seen_dirs: set[str] = set()

    # Maven 项目
    for pom_path in repo_root.rglob("pom.xml"):
        if should_skip(pom_path):
            continue
        artifact_id, packaging = parse_pom(pom_path)
        rel = safe_relative(pom_path.parent, repo_root)
        if rel not in seen_dirs:
            seen_dirs.add(rel)
            modules.append({
                "module": pom_path.parent.name,
                "artifact_id": artifact_id or pom_path.parent.name,
                "packaging": packaging or "",
                "build": "Maven",
                "path": rel,
            })

    # Gradle 项目
    for gradle_name in ["build.gradle", "build.gradle.kts"]:
        for gradle_path in repo_root.rglob(gradle_name):
            if should_skip(gradle_path):
                continue
            rel = safe_relative(gradle_path.parent, repo_root)
            if rel in seen_dirs:
                continue
            seen_dirs.add(rel)
            artifact_id, packaging = parse_gradle(gradle_path)
            modules.append({
                "module": gradle_path.parent.name,
                "artifact_id": artifact_id,
                "packaging": packaging,
                "build": "Gradle",
                "path": rel,
            })

    modules.sort(key=lambda item: item["path"])
    return modules


def is_job_or_listener(file_path: Path) -> bool:
    name = file_path.name
    return name.endswith("Job.java") or name.endswith("Listener.java") or name.endswith("Task.java")


def collect_java_signals(
    repo_root: Path, module_dirs: list[Path], limit: int
) -> tuple[list[dict], list[dict], dict[str, dict[str, int]], list[dict], list[dict]]:
    entry_rows: list[dict[str, str]] = []
    signal_rows: list[dict[str, str]] = []
    role_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    table_rows: list[dict[str, str]] = []
    seen_tables: set[str] = set()

    for file_path in repo_root.rglob("*.java"):
        if should_skip(file_path):
            continue

        module_dir = locate_module(module_dirs, file_path)
        module_name = module_dir.name
        relative_path = safe_relative(file_path, repo_root)

        # 角色识别
        matched_role = ""
        for role, suffix in ROLE_SUFFIXES.items():
            if file_path.name.endswith(suffix):
                matched_role = role
                break
        if not matched_role and is_job_or_listener(file_path):
            matched_role = "Job/Listener"

        if matched_role:
            role_counts[module_name][matched_role] += 1
            if len(entry_rows) < limit:
                entry_rows.append({
                    "module": module_name,
                    "type": matched_role,
                    "clazz": file_path.stem,
                    "path": relative_path,
                })

        # 读取文件内容（用于信号和表名检测）
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        # 依赖信号检测（一个文件可以匹配多个信号）
        if len(signal_rows) < limit * 2:
            for signal_name, pattern in SIGNAL_PATTERNS.items():
                if pattern.search(text):
                    signal_rows.append({
                        "module": module_name,
                        "signal": signal_name,
                        "path": relative_path,
                        "note": file_path.stem,
                    })

        # 表名提取
        if len(table_rows) < limit:
            for tp in TABLE_NAME_PATTERNS:
                for m in tp.finditer(text):
                    table_name = m.group(1)
                    if table_name not in seen_tables:
                        seen_tables.add(table_name)
                        table_rows.append({
                            "module": module_name,
                            "table": table_name,
                            "source": file_path.stem,
                            "path": relative_path,
                        })

    # 去重信号（同模块同信号只保留一条）
    seen_signals: set[str] = set()
    deduped_signals: list[dict[str, str]] = []
    for row in signal_rows:
        key = f"{row['module']}:{row['signal']}"
        if key not in seen_signals:
            seen_signals.add(key)
            deduped_signals.append(row)
    signal_rows = deduped_signals[:limit]

    return entry_rows, signal_rows, role_counts, table_rows, []


def collect_mybatis_mappers(repo_root: Path, module_dirs: list[Path], limit: int) -> list[dict[str, str]]:
    """扫描 MyBatis XML Mapper 文件，提取 namespace 和涉及的表名。"""
    mapper_rows: list[dict[str, str]] = []
    table_pattern = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+`?(\w+)`?", re.IGNORECASE)

    for xml_path in repo_root.rglob("*Mapper.xml"):
        if should_skip(xml_path):
            continue
        if len(mapper_rows) >= limit:
            break

        module_dir = locate_module(module_dirs, xml_path)
        try:
            text = xml_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        namespace = ""
        ns_match = re.search(r'namespace\s*=\s*"([^"]+)"', text)
        if ns_match:
            namespace = ns_match.group(1).split(".")[-1]

        tables = set(table_pattern.findall(text))
        # 过滤掉 SQL 关键字误匹配
        tables = {t for t in tables if t.lower() not in {"set", "where", "and", "or", "select", "values"}}

        mapper_rows.append({
            "module": module_dir.name,
            "namespace": namespace or xml_path.stem,
            "tables": ", ".join(sorted(tables)[:5]) if tables else "-",
            "path": safe_relative(xml_path, repo_root),
        })

    return mapper_rows


def collect_spring_configs(repo_root: Path, limit: int) -> list[dict[str, str]]:
    """扫描 Spring Boot 配置文件，提取关键配置项。"""
    config_rows: list[dict[str, str]] = []
    config_patterns = ["application.yml", "application.yaml", "application.properties",
                       "bootstrap.yml", "bootstrap.yaml", "bootstrap.properties",
                       "application-*.yml", "application-*.yaml", "application-*.properties"]

    seen_files: set[str] = set()
    for pattern in config_patterns:
        for config_path in repo_root.rglob(pattern):
            if should_skip(config_path):
                continue
            rel = safe_relative(config_path, repo_root)
            if rel in seen_files:
                continue
            seen_files.add(rel)

            try:
                text = config_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for config_name, regex in CONFIG_KEY_PATTERNS.items():
                m = regex.search(text)
                if m and len(config_rows) < limit:
                    config_rows.append({
                        "config": config_name,
                        "value": m.group(1)[:60],
                        "file": rel,
                    })

    return config_rows


def collect_sql_files(repo_root: Path, limit: int) -> list[dict[str, str]]:
    """扫描仓库中的 SQL 文件。"""
    sql_rows: list[dict[str, str]] = []
    for sql_path in repo_root.rglob("*.sql"):
        if should_skip(sql_path):
            continue
        if len(sql_rows) >= limit:
            break
        try:
            text = sql_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        line_count = len(text.splitlines())
        has_ddl = bool(re.search(r"\b(CREATE|ALTER)\b", text, re.IGNORECASE))
        has_dml = bool(re.search(r"\b(INSERT|UPDATE|DELETE)\b", text, re.IGNORECASE))
        sql_type = []
        if has_ddl:
            sql_type.append("DDL")
        if has_dml:
            sql_type.append("DML")
        sql_rows.append({
            "file": safe_relative(sql_path, repo_root),
            "lines": str(line_count),
            "type": "/".join(sql_type) if sql_type else "其他",
        })
    return sql_rows


def print_markdown(
    modules: list[dict[str, str]],
    entry_rows: list[dict[str, str]],
    signal_rows: list[dict[str, str]],
    role_counts: dict[str, dict[str, int]],
    table_rows: list[dict[str, str]],
    mapper_rows: list[dict[str, str]],
    config_rows: list[dict[str, str]],
    sql_rows: list[dict[str, str]],
    repo_root: Path,
) -> None:
    print("# 轻量仓库扫描结果")
    print()
    print(f"- 仓库根目录：`{repo_root}`")
    print("- 用途：辅助填写 `00-baseline.md`、`01-research.md`、`02-design.md` 中与主项目、主链路、依赖和契约相关的部分")
    print()

    # 1. 模块概览
    print("## 1. 模块概览")
    print()
    print("| 模块 | artifactId | packaging | 构建工具 | 路径 |")
    print("|---|---|---|---|---|")
    for module in modules[:30]:
        print(f"| {module['module']} | {module['artifact_id']} | {module['packaging']} | {module['build']} | `{module['path']}` |")
    if not modules:
        print("| - | - | - | - | 未扫描到构建文件 |")
    print()

    # 2. 代码角色统计
    all_roles = sorted({role for counts in role_counts.values() for role in counts})
    if not all_roles:
        all_roles = ["Controller", "Service", "Facade", "Mapper", "Job/Listener"]
    print("## 2. 代码角色统计")
    print()
    print(f"| 模块 | {' | '.join(all_roles)} |")
    print(f"|---|{'|'.join(['---'] * len(all_roles))}|")
    module_names = sorted({m['module'] for m in modules} | set(role_counts))
    for module_name in module_names[:30]:
        counts = role_counts.get(module_name, {})
        cells = " | ".join(str(counts.get(r, 0)) for r in all_roles)
        print(f"| {module_name} | {cells} |")
    if not module_names:
        cells = " | ".join("0" for _ in all_roles)
        print(f"| - | {cells} |")
    print()

    # 3. 关键入口候选
    print("## 3. 关键入口候选")
    print()
    print("| 模块 | 类型 | 类 | 路径 |")
    print("|---|---|---|---|")
    for row in entry_rows:
        print(f"| {row['module']} | {row['type']} | {row['clazz']} | `{row['path']}` |")
    if not entry_rows:
        print("| - | - | - | 未扫描到候选入口 |")
    print()

    # 4. 依赖信号候选
    print("## 4. 依赖信号候选")
    print()
    print("| 模块 | 信号 | 位置 | 说明 |")
    print("|---|---|---|---|")
    for row in signal_rows:
        print(f"| {row['module']} | {row['signal']} | `{row['path']}` | {row['note']} |")
    if not signal_rows:
        print("| - | - | - | 未扫描到明显依赖信号 |")
    print()

    # 5. 数据库表名（从注解提取）
    if table_rows:
        print("## 5. 数据库表名（注解提取）")
        print()
        print("| 模块 | 表名 | 来源类 | 路径 |")
        print("|---|---|---|---|")
        for row in table_rows:
            print(f"| {row['module']} | {row['table']} | {row['source']} | `{row['path']}` |")
        print()

    # 6. MyBatis Mapper XML
    if mapper_rows:
        print("## 6. MyBatis Mapper XML")
        print()
        print("| 模块 | Namespace | 涉及表 | 路径 |")
        print("|---|---|---|---|")
        for row in mapper_rows:
            print(f"| {row['module']} | {row['namespace']} | {row['tables']} | `{row['path']}` |")
        print()

    # 7. Spring Boot 配置
    if config_rows:
        print("## 7. Spring Boot 关键配置")
        print()
        print("| 配置项 | 值 | 文件 |")
        print("|---|---|---|")
        for row in config_rows:
            print(f"| {row['config']} | `{row['value']}` | `{row['file']}` |")
        print()

    # 8. SQL 文件
    if sql_rows:
        print("## 8. SQL 文件")
        print()
        print("| 文件 | 行数 | 类型 |")
        print("|---|---|---|")
        for row in sql_rows:
            print(f"| `{row['file']}` | {row['lines']} | {row['type']} |")
        print()

    # 回填建议
    print("## 回填建议")
    print()
    print("- Intake 阶段可先用它辅助判断主项目和关键依赖项目")
    print("- Alignment / Design 阶段再把真实入口、依赖调用和关键表落点回填到研究或设计文档")
    print("- 只把能确认的事实写进需求文档，扫描结果只是候选，不直接等于结论")
    print("- 表名和 Mapper 信息可辅助 04-schema.sql 的设计")
    print("- 配置信息可辅助判断中间件依赖和部署环境")


def main() -> None:
    parser = argparse.ArgumentParser(description="轻量扫描仓库中的模块、入口和依赖信号")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--feature-dir", help="需求目录，用于自动定位仓库根目录")
    group.add_argument("--repo-root", help="仓库根目录")
    parser.add_argument("--limit", type=int, default=20, help="每类结果最多输出多少行")
    args = parser.parse_args()

    repo_root = detect_repo_root(Path(args.feature_dir).resolve()) if args.feature_dir else Path(args.repo_root).resolve()
    limit = max(1, args.limit)

    modules = collect_modules(repo_root)
    module_dirs = [repo_root / Path(m["path"]) for m in modules]
    entry_rows, signal_rows, role_counts, table_rows, _ = collect_java_signals(repo_root, module_dirs, limit)
    mapper_rows = collect_mybatis_mappers(repo_root, module_dirs, limit)
    config_rows = collect_spring_configs(repo_root, limit)
    sql_rows = collect_sql_files(repo_root, limit)

    print_markdown(modules, entry_rows, signal_rows, role_counts, table_rows,
                   mapper_rows, config_rows, sql_rows, repo_root)


if __name__ == "__main__":
    main()
