#!/usr/bin/env python3
"""在已确认的目标项目或模块内执行有文件数、深度和输出边界的候选扫描。"""

from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


EXCLUDED_DIRS = {
    ".git", ".idea", ".gradle", ".mvn", ".vscode", "node_modules",
    "target", "build", "out", "dist", "ggg",
}

ROLE_SUFFIXES = {
    "Controller": "Controller.java", "ServiceImpl": "ServiceImpl.java",
    "Service": "Service.java", "Facade": "Facade.java", "Provider": "Provider.java",
    "Mapper": "Mapper.java", "Repository": "Repository.java", "Manager": "Manager.java",
    "Handler": "Handler.java", "Converter": "Converter.java", "DTO": "DTO.java", "VO": "VO.java",
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

TABLE_NAME_PATTERNS = [
    re.compile(r'@TableName\s*\(\s*"([^"]+)"'),
    re.compile(r'@TableName\s*\(\s*value\s*=\s*"([^"]+)"'),
    re.compile(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"'),
]

# 只用于判断某类配置是否存在。禁止捕获、保存或输出等号/冒号右侧的配置值。
CONFIG_KEY_PATTERNS = {
    "端口": re.compile(r"(?m)^\s*server\.port\s*[:=]"),
    "数据源URL": re.compile(r"(?m)^\s*(?:spring\.datasource|datasource).*url\s*[:=]"),
    "Redis": re.compile(r"(?m)^\s*spring\.(?:data\.)?redis\.host\s*[:=]"),
    "Dubbo应用名": re.compile(r"(?m)^\s*dubbo\.application\.name\s*[:=]"),
    "Dubbo注册中心": re.compile(r"(?m)^\s*dubbo\.registry\.address\s*[:=]"),
    "Nacos": re.compile(r"(?m)^\s*spring\.cloud\.nacos\.(?:discovery|config)\.server-addr\s*[:=]"),
    "MQ-NameServer": re.compile(r"(?m)^\s*rocketmq\.name-server\s*[:=]"),
}

CONFIG_NAMES = {
    "application.yml", "application.yaml", "application.properties",
    "bootstrap.yml", "bootstrap.yaml", "bootstrap.properties",
}


def safe_relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def collect_scoped_files(root: Path, max_files: int, max_depth: int) -> tuple[list[Path], bool]:
    """只建立一次受控文件清单；后续所有分析都不得越过该清单。"""
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS and depth < max_depth and not (current_path / d).is_symlink()
        )
        for name in sorted(names):
            path = current_path / name
            if path.is_symlink():
                continue
            if len(files) >= max_files:
                return files, True
            files.append(path)
    return files, False


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def parse_pom(path: Path) -> tuple[str, str]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return "", ""
    artifact_id = ""
    packaging = "jar"
    for node in list(root):
        tag = node.tag.split("}", 1)[-1]
        if tag == "artifactId" and node.text:
            artifact_id = node.text.strip()
        elif tag == "packaging" and node.text:
            packaging = node.text.strip()
    return artifact_id, packaging


def parse_gradle(path: Path) -> tuple[str, str]:
    text = read_text(path)
    match = re.search(r"archivesBaseName\s*=\s*['\"]([^'\"]+)['\"]", text)
    artifact = match.group(1) if match else path.parent.name
    packaging = "war" if re.search(r"(?:id\s*[(']\s*['\"]war|apply plugin.*war)", text, re.I) else "jar"
    return artifact, packaging


def collect_modules(files: list[Path], root: Path) -> list[dict[str, str]]:
    modules: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in files:
        if path.name not in {"pom.xml", "build.gradle", "build.gradle.kts"} or path.parent in seen:
            continue
        seen.add(path.parent)
        artifact, packaging = parse_pom(path) if path.name == "pom.xml" else parse_gradle(path)
        modules.append({
            "module": path.parent.name,
            "artifact_id": artifact or path.parent.name,
            "packaging": packaging or "jar",
            "build": "Maven" if path.name == "pom.xml" else "Gradle",
            "path": safe_relative(path.parent, root),
        })
    return sorted(modules, key=lambda item: item["path"])


def locate_module(module_dirs: list[Path], path: Path) -> Path:
    matches = [directory for directory in module_dirs if directory == path.parent or directory in path.parents]
    return max(matches, key=lambda item: len(item.parts)) if matches else path.parent


def collect_java(files: list[Path], root: Path, module_dirs: list[Path], limit: int):
    entries: list[dict[str, str]] = []
    signals: list[dict[str, str]] = []
    role_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    tables: list[dict[str, str]] = []
    seen_signals: set[tuple[str, str]] = set()
    seen_tables: set[str] = set()
    for path in files:
        if path.suffix != ".java":
            continue
        module = locate_module(module_dirs, path).name
        rel = safe_relative(path, root)
        role = next((name for name, suffix in ROLE_SUFFIXES.items() if path.name.endswith(suffix)), "")
        if not role and path.name.endswith(("Job.java", "Listener.java", "Task.java")):
            role = "Job/Listener"
        if role:
            role_counts[module][role] += 1
            if len(entries) < limit:
                entries.append({"module": module, "type": role, "clazz": path.stem, "path": rel})
        text = read_text(path)
        for signal, pattern in SIGNAL_PATTERNS.items():
            key = (module, signal)
            if len(signals) < limit and key not in seen_signals and pattern.search(text):
                seen_signals.add(key)
                signals.append({"module": module, "signal": signal, "path": rel, "note": path.stem})
        for pattern in TABLE_NAME_PATTERNS:
            for match in pattern.finditer(text):
                table = match.group(1)
                if len(tables) < limit and table not in seen_tables:
                    seen_tables.add(table)
                    tables.append({"module": module, "table": table, "source": path.stem, "path": rel})
    return entries, signals, role_counts, tables


def collect_mappers(files: list[Path], root: Path, module_dirs: list[Path], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    table_pattern = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+`?(\w+)`?", re.I)
    for path in files:
        if len(rows) >= limit or not path.name.endswith("Mapper.xml"):
            continue
        text = read_text(path)
        namespace_match = re.search(r'namespace\s*=\s*"([^"]+)"', text)
        tables = {name for name in table_pattern.findall(text) if name.lower() not in {"set", "where", "select", "values"}}
        rows.append({
            "module": locate_module(module_dirs, path).name,
            "namespace": namespace_match.group(1).split(".")[-1] if namespace_match else path.stem,
            "tables": ", ".join(sorted(tables)[:5]) or "-",
            "path": safe_relative(path, root),
        })
    return rows


def is_config_file(path: Path) -> bool:
    return path.name in CONFIG_NAMES or bool(re.fullmatch(r"(?:application|bootstrap)-.+\.(?:yml|yaml|properties)", path.name))


def collect_configs(files: list[Path], root: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in files:
        if len(rows) >= limit or not is_config_file(path):
            continue
        text = read_text(path)
        for config, pattern in CONFIG_KEY_PATTERNS.items():
            if len(rows) < limit and pattern.search(text):
                rows.append({"config": config, "file": safe_relative(path, root)})
    return rows


def collect_sql(files: list[Path], root: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in files:
        if len(rows) >= limit or path.suffix.lower() != ".sql":
            continue
        text = read_text(path)
        kinds = []
        if re.search(r"\b(?:CREATE|ALTER)\b", text, re.I):
            kinds.append("DDL")
        if re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", text, re.I):
            kinds.append("DML")
        rows.append({"file": safe_relative(path, root), "lines": str(len(text.splitlines())), "type": "/".join(kinds) or "其他"})
    return rows


def print_table(headers: list[str], rows: list[list[str]], empty: list[str]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join("---" for _ in headers) + "|")
    for row in rows or [empty]:
        print("| " + " | ".join(row) + " |")
    print()


def print_markdown(root: Path, files: list[Path], truncated: bool, max_files: int, max_depth: int,
                   modules, entries, signals, role_counts, tables, mappers, configs, sql_rows) -> None:
    print("# 有界代码候选扫描结果\n")
    print(f"- 扫描范围：`{root}`")
    print(f"- 实际纳入文件数：{len(files)}；文件上限：{max_files}；目录深度上限：{max_depth}")
    print(f"- 扫描是否因文件上限截断：{'是' if truncated else '否'}")
    print("- 用途：仅补充入口、依赖和数据落点候选；不得把候选直接当作代码结论\n")

    print("## 1. 模块概览\n")
    print_table(["模块", "artifactId", "packaging", "构建工具", "路径"],
                [[m["module"], m["artifact_id"], m["packaging"], m["build"], f'`{m["path"]}`'] for m in modules],
                ["-", "-", "-", "-", "未扫描到构建文件"])
    print("## 2. 代码角色统计\n")
    roles = sorted({role for counts in role_counts.values() for role in counts}) or ["Controller", "Service", "Facade", "Mapper", "Job/Listener"]
    module_names = sorted({m["module"] for m in modules} | set(role_counts))
    print_table(["模块", *roles], [[name, *[str(role_counts[name].get(role, 0)) for role in roles]] for name in module_names], ["-", *["0" for _ in roles]])
    print("## 3. 关键入口候选\n")
    print_table(["模块", "类型", "类", "路径"], [[r["module"], r["type"], r["clazz"], f'`{r["path"]}`'] for r in entries], ["-", "-", "-", "未扫描到候选入口"])
    print("## 4. 依赖信号候选\n")
    print_table(["模块", "信号", "位置", "说明"], [[r["module"], r["signal"], f'`{r["path"]}`', r["note"]] for r in signals], ["-", "-", "-", "未扫描到明显依赖信号"])
    if tables:
        print("## 5. 数据库表名（注解提取）\n")
        print_table(["模块", "表名", "来源类", "路径"], [[r["module"], r["table"], r["source"], f'`{r["path"]}`'] for r in tables], ["-", "-", "-", "-"])
    if mappers:
        print("## 6. MyBatis Mapper XML\n")
        print_table(["模块", "Namespace", "涉及表", "路径"], [[r["module"], r["namespace"], r["tables"], f'`{r["path"]}`'] for r in mappers], ["-", "-", "-", "-"])
    if configs:
        print("## 7. Spring Boot 关键配置\n")
        print_table(["配置项", "文件"], [[r["config"], f'`{r["file"]}`'] for r in configs], ["-", "-"])
        print("配置扫描只报告配置类别和文件位置，不读取到输出、不保存配置值。\n")
    if sql_rows:
        print("## 8. SQL 文件\n")
        print_table(["文件", "行数", "类型"], [[f'`{r["file"]}`', r["lines"], r["type"]] for r in sql_rows], ["-", "-", "-"])
    print("## 回填规则\n")
    print("- 只有 CodeGraph 无法定位入口或已知模块边界内仍缺候选时才使用扫描器")
    print("- 文件清单被截断时必须缩小 scope 后重扫，不得据此声明未发现")
    print("- 扫描命中必须继续核对真实调用链，再以代码证据写入需求文档")


def bounded_positive(value: int, name: str, upper: int) -> int:
    if value < 1 or value > upper:
        raise SystemExit(f"{name} 必须在 1..{upper} 之间")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="在已确认的目标项目或模块内扫描入口和依赖候选")
    parser.add_argument("--scope-root", required=True, help="已确认的目标项目或模块目录；不得传多项目仓库父目录")
    parser.add_argument("--max-files", type=int, default=500, help="实际纳入扫描的文件上限，默认 500，最大 5000")
    parser.add_argument("--max-depth", type=int, default=8, help="相对 scope-root 的目录深度上限，默认 8，最大 20")
    parser.add_argument("--limit", type=int, default=20, help="每类结果最多展示行数，默认 20，最大 200")
    args = parser.parse_args()

    root = Path(args.scope_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"扫描范围不存在或不是目录: {root}")
    if (root / "ggg" / "features").exists():
        raise SystemExit("拒绝扫描包含 ggg/features 的仓库根目录；请把 --scope-root 缩小到已确认的目标项目或模块")
    max_files = bounded_positive(args.max_files, "--max-files", 5000)
    max_depth = bounded_positive(args.max_depth, "--max-depth", 20)
    limit = bounded_positive(args.limit, "--limit", 200)

    files, truncated = collect_scoped_files(root, max_files, max_depth)
    modules = collect_modules(files, root)
    module_dirs = [root / Path(module["path"]) for module in modules]
    entries, signals, role_counts, tables = collect_java(files, root, module_dirs, limit)
    mappers = collect_mappers(files, root, module_dirs, limit)
    configs = collect_configs(files, root, limit)
    sql_rows = collect_sql(files, root, limit)
    print_markdown(root, files, truncated, max_files, max_depth, modules, entries, signals,
                   role_counts, tables, mappers, configs, sql_rows)


if __name__ == "__main__":
    main()
