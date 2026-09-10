# -*- coding: utf-8 -*-
"""交付包复现入口（模板）。放在交付目录根，解包后一条命令跑通：

    python reproduce.py              # 完整复核并运行最小可核子集
    python reproduce.py --check-only # 仅诊断完整性；不算 P7 复现通过

若根目录有 delivery-manifest.json，本模板按比赛交付结构检查论文 PDF、
支撑材料、完整源码入口和条件化的 AI 详情 PDF；没有该清单时兼容旧版目录。
默认入口必须真的运行至少一个最小重算命令，不能只检查文件是否存在。
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 旧版包的只读复核项：(说明, 相对路径) —— 缺一个即 fail。
# 新版比赛包由 delivery-manifest.json 声明并由 check_manifest_package() 复核。
REQUIRED = [
    ("论文 PDF", "论文/main.pdf"),
    ("论文源", "论文/main.tex"),
    ("数值宏", "论文/numbers.tex"),
    ("结果台账", "结果/results_ledger.json"),
    ("图目录", "图"),
    ("求解代码", "求解"),
]

# 重算项：(说明, 命令) —— 每条应在数分钟内跑完，且写回可比对的结果文件。
RECOMPUTE = [
    # ("Q1 最小复算", [sys.executable, "支撑材料/source/main.py"]),
]

RUNTIME_IDENTITY_FIELDS = ("problem", "version", "convention", "core_commit", "environment")
RUNTIME_CHECK_FIELDS = {
    "input": ("input", "inputs"),
    "decision": ("decision", "verdict", "判定"),
    "certificate": ("certificate", "证书"),
    "seed": ("seed", "seeds"),
    "source": ("source", "sources"),
}


def _is_manifest_package():
    return os.path.isfile(os.path.join(HERE, "delivery-manifest.json"))


def _safe_manifest_path(relative):
    if not isinstance(relative, str) or not relative.strip() or "\\" in relative:
        return None
    if os.path.isabs(relative) or relative.startswith("~"):
        return None
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    target = os.path.abspath(os.path.join(HERE, *parts))
    try:
        if os.path.commonpath((HERE, target)) != HERE:
            return None
    except ValueError:
        return None
    return target


def check_manifest_package():
    """基础复核新版比赛交付包；完整关系由 scripts/delivery_gate.py 再检查。"""
    manifest_path = os.path.join(HERE, "delivery-manifest.json")
    bad = []
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print("  FAIL 清单无法读取:", exc)
        return ["delivery-manifest.json"]

    def require_file(label, relative):
        path = _safe_manifest_path(relative)
        ok = bool(path and os.path.isfile(path))
        print(("  OK   " if ok else "  MISS ") + f"{label}: {relative}")
        if not ok:
            bad.append(str(relative))
        return path

    def require_dir(label, relative):
        path = _safe_manifest_path(relative)
        ok = bool(path and os.path.isdir(path))
        print(("  OK   " if ok else "  MISS ") + f"{label}: {relative}")
        if not ok:
            bad.append(str(relative))
        return path

    paper = manifest.get("paper_pdf")
    support_root = manifest.get("support_root")
    require_file("论文 PDF", paper)
    require_dir("支撑材料", support_root)

    reproduction = manifest.get("reproduction")
    if not isinstance(reproduction, dict):
        bad.append("reproduction")
        print("  MISS reproduction")
    else:
        require_file("复现入口", reproduction.get("entrypoint"))
        if not isinstance(reproduction.get("command"), str) or not reproduction["command"].strip():
            bad.append("reproduction.command")
            print("  MISS reproduction.command")

    source_items = []
    for item in manifest.get("support_items", []):
        if isinstance(item, dict) and item.get("kind") == "source_code":
            source_items.append(item)
    if not source_items:
        bad.append("support_items.source_code")
        print("  MISS 完整源码条目")
    for item in source_items:
        source_dir = item.get("path")
        require_dir("完整源码目录", source_dir)
        if item.get("coverage") != "complete_runnable_source":
            bad.append("source_code.coverage")
            print("  MISS source_code.coverage")
        entrypoints = item.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            bad.append("source_code.entrypoints")
            print("  MISS source_code.entrypoints")
        else:
            for entrypoint in entrypoints:
                require_file("源码入口", entrypoint)

    ai_use = manifest.get("ai_use")
    if not isinstance(ai_use, dict) or not isinstance(ai_use.get("used"), bool):
        bad.append("ai_use.used")
        print("  MISS ai_use.used")
    elif ai_use["used"]:
        require_file("AI 工具使用详情", ai_use.get("details_pdf"))
    elif ai_use.get("details_pdf") not in (None, ""):
        bad.append("ai_use.details_pdf")
        print("  FAIL 未使用 AI 时不得声明 AI 详情 PDF")

    return bad


def check_exists():
    if _is_manifest_package():
        return check_manifest_package()
    bad = []
    for label, rel in REQUIRED:
        p = os.path.join(HERE, rel)
        ok = os.path.exists(p)
        print(("  OK   " if ok else "  MISS ") + f"{label}: {rel}")
        if not ok:
            bad.append(rel)
    return bad


def _load_json(path, label, bad):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        bad.append(f"{label} JSON 无法读取：{exc}")
        return None


def _question_name(value):
    name = os.path.basename(str(value).strip())
    return name if name.lower().endswith(".json") else name + ".json"


def check_runtime():
    """校验旧版运行时链；新版比赛包由 manifest 和实际复算承担。"""
    if _is_manifest_package():
        print("  N/A  新版交付包不使用旧版运行时 JSON 链")
        return []
    runtime = os.path.join(HERE, "结果", "运行时")
    bad = []
    identity_path = os.path.join(runtime, "model_identity.json")
    aggregate_path = os.path.join(runtime, "aggregate.json")
    for label, path in (("model_identity", identity_path), ("aggregate", aggregate_path)):
        if not os.path.isfile(path):
            bad.append(f"运行时工件缺失：结果/运行时/{os.path.basename(path)}")
    if bad:
        for item in bad:
            print("  MISS ", item)
        return bad

    identity = _load_json(identity_path, "model_identity", bad)
    aggregate = _load_json(aggregate_path, "aggregate", bad)
    if not isinstance(identity, dict):
        bad.append("model_identity 必须是 JSON 对象")
    else:
        for field in RUNTIME_IDENTITY_FIELDS:
            if identity.get(field) in (None, "", [], {}):
                bad.append(f"model_identity 缺非空字段 {field}")
    if not isinstance(aggregate, dict):
        bad.append("aggregate 必须是 JSON 对象")
        aggregate = {}
    if not isinstance(aggregate.get("checks"), dict) or not aggregate["checks"]:
        bad.append("aggregate.checks 必须是非空对象")

    q_paths = sorted(glob.glob(os.path.join(runtime, "q*.json")))
    q_files = {os.path.basename(path): path for path in q_paths}
    if not q_files:
        bad.append("结果/运行时/缺少逐问 qN.json")

    declared = aggregate.get("questions")
    if isinstance(declared, dict):
        declared_names = {_question_name(name) for name in declared}
    elif isinstance(declared, list):
        declared_names = {_question_name(name) for name in declared}
    else:
        declared_names = set()
        bad.append("aggregate.questions 必须是逐问文件名列表或对象")
    for name in sorted(set(q_files) - declared_names):
        bad.append(f"aggregate 未引用逐问工件：{name}")
    for name in sorted(declared_names - set(q_files)):
        bad.append(f"aggregate 引用了不存在的逐问工件：{name}")

    for name, path in q_files.items():
        question = _load_json(path, name, bad)
        if not isinstance(question, dict):
            bad.append(f"{name} 必须是 JSON 对象")
            continue
        checks = question.get("checks")
        if not isinstance(checks, dict) or not checks:
            bad.append(f"{name} 缺非空 checks 对象")
            continue
        for label, aliases in RUNTIME_CHECK_FIELDS.items():
            if not any(checks.get(key) not in (None, "", [], {}) for key in aliases):
                bad.append(f"{name}.checks 缺非空字段 {label}")
    if bad:
        for item in bad:
            print("  FAIL ", item)
    else:
        print(f"  OK   运行时链：1 identity + {len(q_files)} qN + aggregate")
    return bad


def check_ledger():
    """台账自洽 + 论文宏与台账逐条比对。"""
    if _is_manifest_package():
        print("  N/A  新版交付包按 manifest 与实际复算复核")
        return []
    lp = os.path.join(HERE, "结果/results_ledger.json")
    np_ = os.path.join(HERE, "论文/numbers.tex")
    if not (os.path.exists(lp) and os.path.exists(np_)):
        return ["台账或 numbers.tex 缺失，跳过一致性比对"]
    led = json.load(open(lp, encoding="utf-8"))
    tex = open(np_, encoding="utf-8").read()
    problems = []
    for key, e in led.items():
        if e.get("role") == "intermediate":
            continue
        disp = str(e.get("display", ""))
        if disp and disp not in tex:
            problems.append(f"台账条目 {key} 的值 {disp} 未出现在 numbers.tex")
        if e.get("status") == "stale":
            problems.append(f"台账条目 {key} 状态为 stale，不得被论文引用")
    print(f"  台账条目 {len(led)} 条，比对问题 {len(problems)} 条")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true",
                    help="兼容旧调用；默认入口已经执行最小可核子集")
    ap.add_argument("--check-only", action="store_true",
                    help="只检查交付物与运行时链；显式诊断模式，不代表 P7 复现通过")
    a = ap.parse_args()

    print("== 1. 交付物完整性 ==")
    bad = check_exists()
    if _is_manifest_package():
        print("== 2. 交付清单与复现边界 ==")
    else:
        print("== 运行时合同链 ==")
    bad.extend(check_runtime())
    print("== 3. 台账与论文数字一致性 ==")
    problems = check_ledger()

    if not a.check_only:
        print("== 3. 重算最小可核子集 ==")
        for label, cmd in RECOMPUTE:
            print(f"  -> {label}")
            r = subprocess.run(cmd, cwd=HERE)
            if r.returncode != 0:
                problems.append(f"重算失败：{label}")
        if not RECOMPUTE:
            print("  （未配置重算项：交付前必须填 RECOMPUTE，否则 repro 维不完整）")
            problems.append("RECOMPUTE 为空")
    else:
        print("== 3. 重算最小可核子集 ==")
        print("  （--check-only：跳过重算；此模式不构成 P7 复现通过）")

    print("\n== 结论 ==")
    if bad or problems:
        for x in bad:
            print("  FAIL 缺文件:", x)
        for x in problems:
            print("  FAIL", x)
        return 1
    print("  PASS 交付物自洽")
    return 0


if __name__ == "__main__":
    sys.exit(main())
