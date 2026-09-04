# -*- coding: utf-8 -*-
"""官方脚本的契约测试。

为什么必须有这个文件
--------------------
SKILL.md 里写着「官方脚本不可替代」——但一份独立 CR 指出：
这些脚本并没有兑现自己文档里承诺的行为（`certify.py` 在真实临界点上不输出三态 JSON、
`figqa.py` 不展开 `\\input` 导致对分节论文全面误判）。
**在契约测试通过之前，"官方、不可替代"是虚假确定性。**

跑法：
    python -m pytest skill/scripts/tests/test_contracts.py -q
    （无 pytest 时：python skill/scripts/tests/test_contracts.py）
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
PY = sys.executable
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")


def run(script, *args):
    r = subprocess.run([PY, os.path.join(SCRIPTS, script), *map(str, args)],
                       capture_output=True, env=ENV)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def as_json(text):
    i, j = text.find("{"), text.rfind("}")
    assert i >= 0 and j > i, f"输出里没有 JSON：{text[:200]}"
    return json.loads(text[i:j + 1])


# ---------------------------------------------------------------- certify 三态契约
def test_certify_feasible():
    code, out, _ = run("certify.py", "--k", 36108, "--n", 40000, "--threshold", 0.90)
    d = as_json(out)
    assert d["verdict"] == "feasible" and d["pass"] is True and code == 0


def test_certify_excluded():
    code, out, _ = run("certify.py", "--k", 0, "--n", 500, "--threshold", 0.90)
    d = as_json(out)
    assert d["verdict"] == "excluded" and code == 1


def test_certify_inconclusive_gives_needed_n():
    """区间跨阈值且点估计高于阈值：必须给出还需多少样本。"""
    code, out, _ = run("certify.py", "--k", 18054, "--n", 20000, "--threshold", 0.90)
    d = as_json(out)
    assert d["verdict"] == "inconclusive" and code == 1
    assert isinstance(d.get("n_needed_critical"), int) and d["n_needed_critical"] > 20000


def test_certify_always_emits_verdict_even_when_unsolvable():
    """点估计不高于阈值时无解——但仍必须输出完整 verdict JSON，不得中途退出。

    这条正是 CR 抓到的破口：原实现只打一行错误信息，三态协议根本没输出。
    """
    code, out, _ = run("certify.py", "--k", 4490, "--n", 5000, "--threshold", 0.90)
    d = as_json(out)
    assert d["verdict"] == "inconclusive"
    assert d["n_needed_critical"] is None
    assert "inconclusive_note" in d


def test_certify_bounds_ordered():
    for k, n in ((1, 100), (50, 100), (99, 100)):
        _, out, _ = run("certify.py", "--k", k, "--n", n, "--threshold", 0.5)
        d = as_json(out)
        assert 0.0 <= d["bound"] <= d["p_hat"] <= d["upper"] <= 1.0, (k, n, d)


# ---------------------------------------------------------------- figqa 契约
def _make_paper(tmp, referenced_in_section=True):
    os.makedirs(os.path.join(tmp, "论文"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "图"), exist_ok=True)
    io.open(os.path.join(tmp, "论文", "main.tex"), "w", encoding="utf-8").write(
        "\\documentclass{article}\n\\begin{document}\n\\input{sec1.tex}\n\\end{document}\n")
    body = "\\section{S}\n"
    if referenced_in_section:
        body += "\\includegraphics[width=0.8\\linewidth]{fig_used.png}\n"
    io.open(os.path.join(tmp, "论文", "sec1.tex"), "w", encoding="utf-8").write(body)
    for name in ("fig_used.png", "fig_orphan.png"):
        io.open(os.path.join(tmp, "图", name), "wb").write(b"\x89PNG\r\n\x1a\n" + b"x" * 6000)


def test_figqa_expands_input():
    """main.tex 只有 \\input 时，必须能找到分节文件里的引用（否则对分节论文全面误判）。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        _, out, _ = run("figqa.py", os.path.join(tmp, "图"),
                        "--tex", os.path.join(tmp, "论文", "main.tex"),
                        "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"))
        rep = json.load(io.open(out_json, encoding="utf-8"))
        unref = [f for f in rep["figures"]
                 if any("未被正文" in m for m in f["fail"] + f["warn"])]
        names = {f["file"] for f in unref}
        assert "fig_used.png" not in names, "被分节文件引用的图不得判为未引用"
        assert "fig_orphan.png" in names, "未被任何地方引用的图必须判出来"


def test_figqa_unreferenced_is_fail_not_warn():
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        run("figqa.py", os.path.join(tmp, "图"), "--tex", os.path.join(tmp, "论文", "main.tex"),
            "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"))
        rep = json.load(io.open(out_json, encoding="utf-8"))
        orphan = next(f for f in rep["figures"] if f["file"] == "fig_orphan.png")
        assert any("未被正文" in m for m in orphan["fail"]), "未引用必须是 FAIL 不是 WARN"


# ---------------------------------------------------------------- ledger 契约
def test_ledger_requires_scenario_id():
    """authoritative 条目缺语义主键必须 FAIL（防"按位置贴标签"那类事故）。"""
    with tempfile.TemporaryDirectory() as tmp:
        led = {"qX": {"quantity": "p", "unit": "%", "display": "7.50", "role": "authoritative",
                      "status": "frozen",
                      "source": {"script": "s.py", "params": "n=1", "file": "r.json", "field": "p"}}}
        p = os.path.join(tmp, "led.json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(led, ensure_ascii=False))
        code, out, _ = run("ledger.py", "--validate", p)
        assert code == 1 and "scenario_id" in out


# ---------------------------------------------------------------- degenerate 契约
def test_degenerate_flags_single_body_conduction():
    with tempfile.TemporaryDirectory() as tmp:
        mod = os.path.join(tmp, "m.py")
        io.open(mod, "w", encoding="utf-8").write(
            "def conducts(n, threshold, seed):\n"
            "    return n >= 1\n")           # 单体即导通：必须被抓出来
        code, out, _ = run("degenerate.py", "--fn", mod + ":conducts",
                           "--threshold", 1.8, "--trials", 20,
                           "--out", os.path.join(tmp, "g.json"))
        assert code == 1 and "n=1" in out


def test_degenerate_passes_clean_model():
    with tempfile.TemporaryDirectory() as tmp:
        mod = os.path.join(tmp, "m.py")
        io.open(mod, "w", encoding="utf-8").write(
            "def conducts(n, threshold, seed):\n"
            "    return n >= 10 and threshold > 1.0\n")
        code, _, _ = run("degenerate.py", "--fn", mod + ":conducts",
                         "--threshold", 1.8, "--trials", 20,
                         "--out", os.path.join(tmp, "g.json"))
        assert code == 0, "行为正常的模型不得被误判"


# ---------------------------------------------------------------- pkg_scan 契约
def test_pkg_scan_blocks_credential_and_abspath():
    with tempfile.TemporaryDirectory() as tmp:
        io.open(os.path.join(tmp, "run.py"), "w", encoding="utf-8").write(
            "USER, PWD = 'root', 'hunter2hunter2'\nP = 'F:\\\\somewhere\\\\x'\n")
        code, out, _ = run("pkg_scan.py", tmp, "--out", os.path.join(tmp, "s.json"))
        rep = json.load(io.open(os.path.join(tmp, "s.json"), encoding="utf-8"))
        kinds = {b["类型"] for b in rep["blocking"]}
        assert code == 1 and "疑似凭据" in kinds and "绝对路径" in kinds


def test_pkg_scan_clean_package_passes():
    with tempfile.TemporaryDirectory() as tmp:
        io.open(os.path.join(tmp, "ok.py"), "w", encoding="utf-8").write(
            "import os\nP = os.path.join('结果', 'x.json')\n")
        code, _, _ = run("pkg_scan.py", tmp, "--out", os.path.join(tmp, "s.json"))
        assert code == 0, "干净的包不得被误判"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            bad += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            bad += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n契约测试：{len(fns) - bad}/{len(fns)} 通过")
    sys.exit(1 if bad else 0)
