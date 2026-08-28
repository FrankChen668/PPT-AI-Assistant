#!/usr/bin/env python3
"""
Workbench 启动脚本。
从项目根目录的 .env 加载环境变量，然后启动 Workbench 服务器。

用法：
    python start_workbench.py

默认访问：
    http://localhost:8765

可信办公室内网共享需要显式设置 WORKBENCH_HOST=0.0.0.0，且当前没有认证、授权或用户数据隔离。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def load_env(path: Path) -> None:
    """读取 .env 文件并写入 os.environ（不覆盖已有变量）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_env(ROOT / ".env")

    # 把项目根加入路径，确保 workbench 包可导入。workbench package 在没有
    # 显式 WORKBENCH_HOST 时使用 127.0.0.1；.env 中的显式 LAN 配置保持优先。
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from workbench.healthcheck import run_healthcheck
    result = run_healthcheck()
    if result.get("status") != "pass":
        failed = [k for k, v in result.get("checks", {}).items() if v.get("status") != "pass"]
        print(f"[warn] healthcheck 有项目未通过: {failed}")
        print("       继续启动，但部分功能可能不可用。")

    print("启动 Workbench...")

    from workbench import server
    server.main()


if __name__ == "__main__":
    main()
