#!/usr/bin/env python
"""
快速健康检查脚本 - 验证 ICCDDS 后端的可用性。

使用:
    python health_check.py
"""
import sys
import subprocess
from pathlib import Path

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(msg: str):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{msg:^60}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def check(condition: bool, msg: str):
    if condition:
        print(f"{GREEN}✓{RESET} {msg}")
        return True
    else:
        print(f"{RED}✗{RESET} {msg}")
        return False


def main():
    print_header("ICCDDS 后端健康检查")

    all_pass = True

    # 1. Python 版本
    print(f"{YELLOW}1. Python 环境{RESET}")
    py_version = sys.version_info
    py_ok = check(
        py_version.major >= 3 and py_version.minor >= 10,
        f"Python 版本: {sys.version.split()[0]} (需要 3.10+)"
    )
    all_pass = all_pass and py_ok

    # 2. 依赖检查
    print(f"\n{YELLOW}2. 核心依赖包{RESET}")
    dependencies = [
        ("fastapi", "FastAPI"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("celery", "Celery"),
        ("ortools", "Google OR-Tools"),
        ("geoalchemy2", "GeoAlchemy2"),
        ("asyncpg", "asyncpg"),
    ]

    for module_name, display_name in dependencies:
        try:
            __import__(module_name)
            check(True, f"{display_name} 已安装")
        except ImportError:
            check(False, f"{display_name} 缺失 (pip install {module_name})")
            all_pass = False

    # 3. 项目结构
    print(f"\n{YELLOW}3. 项目文件结构{RESET}")
    base_path = Path(__file__).parent
    required_files = [
        ("app/main.py", "FastAPI 入口"),
        ("app/core/config.py", "配置管理"),
        ("app/core/celery_app.py", "Celery 应用"),
        ("app/db/database.py", "数据库连接"),
        ("app/db/schema.sql", "PostgreSQL Schema"),
        ("app/services/solver/solver.py", "OR-Tools Solver"),
        ("app/api/v1/endpoints/optimization.py", "优化 API"),
        ("requirements.txt", "依赖清单"),
    ]

    for file_path, description in required_files:
        full_path = base_path / file_path
        check(full_path.exists(), f"{description}: {file_path}")
        all_pass = all_pass and full_path.exists()

    # 4. Python 编译检查
    print(f"\n{YELLOW}4. Python 代码编译{RESET}")
    py_files_to_check = [
        "app/main.py",
        "app/core/config.py",
        "app/services/solver/solver.py",
        "app/api/v1/endpoints/optimization.py",
    ]

    for py_file in py_files_to_check:
        full_path = base_path / py_file
        try:
            with open(full_path) as f:
                compile(f.read(), str(full_path), 'exec')
            check(True, f"✓ {py_file} 编译正常")
        except SyntaxError as e:
            check(False, f"✗ {py_file} 语法错误: {e}")
            all_pass = False

    # 5. 外部服务检查
    print(f"\n{YELLOW}5. 外部服务{RESET}")

    # PostgreSQL
    try:
        import psycopg2
        print(f"{YELLOW}  PostgreSQL:{RESET}")
        try:
            conn = psycopg2.connect(
                host="localhost",
                user="postgres",
                password="postgres"
            )
            conn.close()
            check(True, "可以连接到 PostgreSQL")
        except Exception as e:
            check(False, f"无法连接: {e}")
            all_pass = False
    except ImportError:
        print(f"{YELLOW}  PostgreSQL:{RESET}")
        check(False, "psycopg2 未安装 (需要访问 PostgreSQL)")

    # Redis
    try:
        import redis
        print(f"{YELLOW}  Redis:{RESET}")
        try:
            r = redis.Redis(host="localhost", port=6379, decode_responses=True)
            r.ping()
            check(True, "可以连接到 Redis")
        except Exception as e:
            check(False, f"无法连接: {e}")
            all_pass = False
    except ImportError:
        print(f"{YELLOW}  Redis:{RESET}")
        check(False, "redis 未安装 (需要 Celery broker)")

    # 6. 启动指南
    print_header("启动说明")

    if not all_pass:
        print(f"{RED}发现问题，请先修复上述错误。{RESET}\n")
        return 1

    print(f"{GREEN}所有检查通过！✓{RESET}\n")
    print("启动后端服务:\n")
    print(f"  {BLUE}1. 启动 Celery Worker (新终端):${RESET}")
    print(f"     celery -A app.core.celery_app worker --loglevel=info\n")

    print(f"  {BLUE}2. 启动 FastAPI (新终端):${RESET}")
    print(f"     uvicorn app.main:app --reload --port 8000\n")

    print(f"  {BLUE}3. 访问 API 文档:${RESET}")
    print(f"     http://localhost:8000/api/v1/docs\n")

    print(f"{GREEN}准备好开始了！🚀{RESET}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
