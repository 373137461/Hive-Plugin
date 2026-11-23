"""根据官方市场索引和仓库清单生成 README 的插件列表。"""

import argparse
from collections import defaultdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- plugins:list:start -->"
END = "<!-- plugins:list:end -->"
CATEGORIES = {
    "system": "系统通用",
    "device": "设备专用",
    "display": "副屏增强",
    "daily": "日常工具",
    "hardware": "硬件工具",
    "enhance": "功能增强",
    "other": "其他",
}


def version_key(version):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("插件和蜂巢版本必须为三段数字")
    return tuple(map(int, version.split(".")))


def code(value):
    if not re.fullmatch(r"[a-z0-9.-]+", value):
        raise ValueError("插件 ID、平台或版本含有非法字符")
    return f"`{value}`"


def cell(text):
    plain = " ".join(text.split())
    return re.sub(r"([\\`*_\[\]()~|])", r"\\\1", escape(plain, quote=False))


def render():
    index = json.loads((ROOT / "hive-market.json").read_bytes())
    manifest_bytes = (ROOT / "hive-repo.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if index["schemaVersion"] != 1 or manifest["schemaVersion"] != 1:
        raise ValueError("市场索引或仓库清单格式不受支持")
    official, = [source for source in index["sources"] if source["kind"] == "official"]
    if official["manifestSha256"].lower() != sha256(manifest_bytes).hexdigest():
        raise ValueError("插件清单的 SHA-256 与官方索引不一致")

    listings = [
        (plugin["id"], release["version"], rid)
        for plugin in official["plugins"]
        for release in plugin["versions"]
        for rid in release["rids"]
    ]
    approved = set(listings)
    if len(approved) != len(listings):
        raise ValueError("官方索引包含重复的插件平台包")

    rows = defaultdict(list)
    for plugin in manifest["plugins"]:
        plugin_id = plugin["id"]
        category = (plugin.get("category") or "").strip().lower()
        if category not in CATEGORIES:
            category = "other"
        for release in plugin["releases"]:
            version = release["version"]
            for target in release["targets"]:
                rid = target["rid"]
                identity = (plugin_id, version, rid)
                if identity not in approved:
                    continue
                approved.remove(identity)
                minimum = target["host"]["minVersion"]
                fields = (cell(plugin["name"]), code(plugin_id), code(rid), code(version), code(minimum), cell(plugin.get("description") or ""))
                order = (version_key(minimum), plugin_id, tuple(-part for part in version_key(version)), rid)
                rows[category].append((order, "| " + " | ".join(fields) + " |"))

    if approved:
        raise ValueError("官方索引中有平台包在仓库清单里找不到")
    sections = []
    for category, name in CATEGORIES.items():
        if rows[category]:
            sections.append("\n".join((
                f"### {name}", "",
                "| 插件 | ID | 平台 | 插件版本 | 最低蜂巢版本 | 简介 |",
                "| --- | --- | --- | --- | --- | --- |",
                *(line for _, line in sorted(rows[category])),
            )))
    return "\n\n".join(sections) or "暂无已上架的插件。"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查 README，保持文件原样")
    args = parser.parse_args()
    path = ROOT / "README.md"
    try:
        current = path.read_text(encoding="utf-8")
        if current.count(START) != 1 or current.count(END) != 1 or current.index(START) > current.index(END):
            raise ValueError("README 中的插件列表标记缺失、重复或顺序错误")
        before = current[:current.index(START) + len(START)]
        after = current[current.index(END):]
        generated = f"{before}\n\n{render()}\n\n{after}"
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"无法生成插件列表（{error}）", file=sys.stderr)
        return 1
    if generated == current:
        return 0
    if args.check:
        print("README 插件列表已过期，请运行 python scripts/update_readme.py 后一起提交。", file=sys.stderr)
        return 1
    path.write_text(generated, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
