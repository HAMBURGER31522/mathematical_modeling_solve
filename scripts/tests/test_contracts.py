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
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def read_repo(relpath):
    with io.open(os.path.join(ROOT, relpath), encoding="utf-8") as f:
        return f.read()


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


def test_figqa_missing_referenced_file_is_fail():
    """正文引用了不存在的图时，不能只按引用字符串计数而通过。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        with io.open(os.path.join(tmp, "论文", "sec1.tex"), "a", encoding="utf-8") as f:
            f.write("\\includegraphics{missing.png}\n")
        out_json = os.path.join(tmp, "r.json")
        code, _, _ = run("figqa.py", os.path.join(tmp, "图"),
                         "--tex", os.path.join(tmp, "论文", "main.tex"),
                         "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"),
                         "--min-figures", "1", "--min-body-figures", "1")
        rep = json.load(io.open(out_json, encoding="utf-8"))
        assert code == 1 and any("不存在" in m for m in rep["top_fail"])


def test_figqa_expands_wildcard_tex_argument():
    """PowerShell 不替 Python 展开通配符，脚本自身必须展开论文/*.tex。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        run("figqa.py", os.path.join(tmp, "图"),
            "--tex", os.path.join(tmp, "论文", "*.tex"),
            "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"),
            "--min-figures", "1", "--min-body-figures", "1")
        rep = json.load(io.open(out_json, encoding="utf-8"))
        unref = [f for f in rep["figures"]
                 if any("未被正文" in m for m in f["fail"] + f["warn"])]
        assert "fig_used.png" not in {f["file"] for f in unref}


# ------------------------------------------------- 体量地板契约（loop2-r3 事故）
# r3 交出 4 张图 / 25 页，逐条满足了当时 skill 的全部硬条件，图表维仍判 0 分：
# 地板定在「能交差」的档，拿到的就是能交差的东西。这几条锁住新档位。

def test_figqa_blocks_too_few_figures():
    """图总数低于 --min-figures 必须 FAIL 且退出码 1。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        rc, _, _ = run("figqa.py", os.path.join(tmp, "图"),
                       "--tex", os.path.join(tmp, "论文", "main.tex"),
                       "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"),
                       "--min-figures", "12", "--min-body-figures", "8")
        rep = json.load(io.open(out_json, encoding="utf-8"))
        assert any("图总数" in m for m in rep["top_fail"]), \
            f"图数不足必须进 top_fail，实际 {rep['top_fail']}"
        assert rc == 1, "图数不足必须退出码 1"


def test_figqa_body_figure_floor_is_separate():
    """把图堆进附录不算数：正文引用数有独立地板。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        run("figqa.py", os.path.join(tmp, "图"),
            "--tex", os.path.join(tmp, "论文", "main.tex"),
            "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"),
            "--min-figures", "1", "--min-body-figures", "8")
        rep = json.load(io.open(out_json, encoding="utf-8"))
        assert any("正文实际引用" in m for m in rep["top_fail"]), \
            "总数达标但正文引用不足时，仍必须 FAIL"


def test_figqa_draft_downgrades_volume_floor():
    """骨架阶段可降级，但只在显式 --draft 下。"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_paper(tmp, referenced_in_section=True)
        out_json = os.path.join(tmp, "r.json")
        run("figqa.py", os.path.join(tmp, "图"),
            "--tex", os.path.join(tmp, "论文", "main.tex"),
            "--out", out_json, "--contact", os.path.join(tmp, "图", "_c.png"),
            "--min-figures", "12", "--draft")
        rep = json.load(io.open(out_json, encoding="utf-8"))
        assert any("图总数" in m for m in rep["top_warn"]), "draft 下应降级为 WARN"
        assert not any("图总数" in m for m in rep["top_fail"])


def _fake_log(tmp, pages=None):
    path = os.path.join(tmp, "main.log")
    body = "This is XeTeX\n"
    if pages is not None:
        body += f"Output written on main.pdf ({pages} pages, 123456 bytes).\n"
    io.open(path, "w", encoding="utf-8").write(body)
    return path


def test_latex_gate_blocks_thin_paper():
    """总页数低于 --min-pages 必须阻断。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=25)
        rc, out, _ = run("latex_gate.py", log, "--min-pages", "40")
        assert rc == 1, "页数不足必须退出码 1"
        assert "总页数 25" in out, out[:300]


def test_latex_gate_unknown_page_count_is_blocking():
    """核不到页数就不能算通过——否则地板被静默跳过（实测踩过）。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=None)
        rc, out, _ = run("latex_gate.py", log, "--min-pages", "40")
        assert rc == 1, "页数取不到必须判 FAIL 而不是 PASS"
        assert "页数无法判定" in out, out[:300]


def test_latex_gate_passes_thick_paper():
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=53)
        rc, _, _ = run("latex_gate.py", log, "--min-pages", "40")
        assert rc == 0, "53 页应当通过"


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


def test_ledger_rejects_incomplete_certificate_metadata():
    """authoritative 证书不能只填 family/pass 而漏掉可回读元数据。"""
    with tempfile.TemporaryDirectory() as tmp:
        led = {"qX": {"value": 0.9, "unit": "1", "display": "90%",
                       "role": "authoritative", "scenario_id": "QX",
                       "status": "frozen",
                       "source": {"script": "s.py", "params": "n=1",
                                  "file": "r.json", "field": "p"},
                       "certificate": {"family": "wilson", "pass": True}}}
        p = os.path.join(tmp, "led.json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(led))
        code, out, _ = run("ledger.py", "--validate", p)
        assert code == 1 and "certificate.bound" in out and "certificate.seed" in out


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


# ---------------------------------------------------------------- EVA gate 契约
EVA_HEADER = "| id | dimension | criterion | artifact | command | exit_code | numbers | applicability | verdict |\n"
EVA_SEPARATOR = "|---|---|---|---|---|---:|---|---|---|\n"
EVA_ROWS = (
    [(f"E{i}", "E", name) for i, name in enumerate((
        "三路独立估计路径", "外部理论量级（Balberg）", "解析算例与暴力对照",
        "误差传导", "多种子临界扫描"), 1)]
    + [(f"V{i}", "V", name) for i, name in enumerate((
        "有限尺寸/胞元形状", "阈值灵敏度系数", "全前沿价格灵敏度"), 1)]
    + [(f"A{i}", "A", name) for i, name in enumerate((
        "上下界夹逼偏差方向", "单位步长整数前沿", "病态切换记录",
        "细长胞元结构反推"), 1)]
)


def _write_eva_matrix(path, root, missing_id=None, bad_exit_id=None):
    rows = [EVA_HEADER, EVA_SEPARATOR]
    for ident, dim, criterion in EVA_ROWS:
        artifact = f"artifact-{ident}.json"
        if ident != missing_id:
            io.open(os.path.join(root, artifact), "w", encoding="utf-8").write("{}")
        exit_code = "zero" if ident == bad_exit_id else "0"
        rows.append(f"| {ident} | {dim} | {criterion} | {artifact} | python check.py {ident} | "
                    f"{exit_code} | n=100, delta=0.01 | applicable | PASS |\n")
    io.open(path, "w", encoding="utf-8").write("".join(rows))


def test_eva_gate_rejects_empty_matrix():
    with tempfile.TemporaryDirectory() as tmp:
        matrix = os.path.join(tmp, "P3-EVA.md")
        review = os.path.join(tmp, "EVA-review.md")
        io.open(matrix, "w", encoding="utf-8").write("# empty\n")
        io.open(review, "w", encoding="utf-8").write("# empty\n")
        code, out, _ = run("eva_gate.py", matrix, "--review", review, "--root", tmp)
        assert code == 1 and "E1" in out


def test_eva_gate_accepts_complete_numeric_matrices():
    with tempfile.TemporaryDirectory() as tmp:
        matrix = os.path.join(tmp, "P3-EVA.md")
        review = os.path.join(tmp, "EVA-review.md")
        _write_eva_matrix(matrix, tmp)
        _write_eva_matrix(review, tmp)
        code, out, _ = run("eva_gate.py", matrix, "--review", review, "--root", tmp)
        assert code == 0 and out.count("解析 12 行") == 2


def test_eva_gate_rejects_missing_artifact_or_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        matrix = os.path.join(tmp, "P3-EVA.md")
        review = os.path.join(tmp, "EVA-review.md")
        _write_eva_matrix(matrix, tmp, missing_id="V2", bad_exit_id="A3")
        _write_eva_matrix(review, tmp)
        os.remove(os.path.join(tmp, "artifact-V2.json"))
        code, out, _ = run("eva_gate.py", matrix, "--review", review, "--root", tmp)
        assert code == 1 and "V2" in out and "A3" in out


def test_eva_gate_accepts_numeric_na_reason_and_checks_its_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        matrix = os.path.join(tmp, "P3-EVA.md")
        review = os.path.join(tmp, "EVA-review.md")
        _write_eva_matrix(matrix, tmp)
        _write_eva_matrix(review, tmp)
        regular = (
            "| E2 | E | 外部理论量级（Balberg） | artifact-E2.json | "
            "python check.py E2 | 0 | n=100, delta=0.01 | applicable | PASS |"
        )
        na = (
            "| E2 | E | 外部理论量级（Balberg） | artifact-E2.json | "
            "python applicability_check.py E2 | 0 | n=0, scale=0 | "
            "N/A: 题目没有随机几何结构，n=0 | N/A |"
        )
        for path in (matrix, review):
            text = io.open(path, encoding="utf-8").read()
            io.open(path, "w", encoding="utf-8").write(text.replace(regular, na))
        code, _, _ = run("eva_gate.py", matrix, "--review", review, "--root", tmp)
        assert code == 0, "带定量理由的 N/A 应是合法记录"

        text = io.open(matrix, encoding="utf-8").read()
        io.open(matrix, "w", encoding="utf-8").write(
            text.replace("artifact-E2.json", "missing-E2.json")
        )
        code, out, _ = run("eva_gate.py", matrix, "--review", review, "--root", tmp)
        assert code == 1 and "E2" in out and "artifact" in out


def _make_reproduce_package(tmp, with_runtime=True):
    import shutil
    shutil.copyfile(os.path.join(ROOT, "skill", "assets", "reproduce.py"),
                    os.path.join(tmp, "reproduce.py"))
    for rel in ("论文/main.pdf", "论文/main.tex", "论文/numbers.tex",
                "结果/results_ledger.json"):
        p = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8").write("{}")
    os.makedirs(os.path.join(tmp, "图"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "求解"), exist_ok=True)
    if with_runtime:
        runtime = os.path.join(tmp, "结果", "运行时")
        os.makedirs(runtime, exist_ok=True)
        identity = {"problem": "demo", "version": "v1", "convention": "c1",
                    "core_commit": "abc", "environment": "test"}
        q = {"checks": {"input": True, "decision": True, "certificate": True,
                         "seed": 1, "source": "solve.py"}}
        aggregate = {"questions": ["q1.json"], "checks": {"q1": True}}
        for name, data in (("model_identity.json", identity), ("q1.json", q),
                           ("aggregate.json", aggregate)):
            io.open(os.path.join(runtime, name), "w", encoding="utf-8").write(
                json.dumps(data, ensure_ascii=False))


def test_reproduce_rejects_missing_runtime_chain():
    with tempfile.TemporaryDirectory() as tmp:
        _make_reproduce_package(tmp, with_runtime=False)
        code, out, _ = subprocess.run([PY, os.path.join(tmp, "reproduce.py"), "--check-only"],
                                       capture_output=True, env=ENV, text=True).returncode, "", ""
        assert code == 1


def test_reproduce_default_rejects_empty_recompute_configuration():
    with tempfile.TemporaryDirectory() as tmp:
        _make_reproduce_package(tmp, with_runtime=True)
        r = subprocess.run([PY, os.path.join(tmp, "reproduce.py")],
                           capture_output=True, env=ENV)
        out = r.stdout.decode("utf-8", "replace")
        assert r.returncode == 1 and "RECOMPUTE 为空" in out


def test_reproduce_accepts_complete_runtime_in_explicit_check_only_mode():
    with tempfile.TemporaryDirectory() as tmp:
        _make_reproduce_package(tmp, with_runtime=True)
        r = subprocess.run([PY, os.path.join(tmp, "reproduce.py"), "--check-only"],
                           capture_output=True, env=ENV)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------- v3.2 E/V/A 证据链契约
def test_skill_requires_v32_evidence_battery():
    text = read_repo("skill/SKILL.md")
    required = (
        "E/V/A 证据包",
        "三路独立估计路径",
        "Balberg",
        "解析算例",
        "暴力对照",
        "误差传导实验",
        "多种子临界扫描",
        "有限尺寸",
        "胞元形状",
        "阈值灵敏度系数",
        "全前沿价格灵敏度",
        "上下界夹逼偏差方向",
        "单位步长整数前沿",
        "病态切换记录",
        "细长胞元",
    )
    missing = [marker for marker in required if marker not in text]
    assert not missing, f"SKILL.md 缺少 v3.2 强制条款: {missing}"
    assert "缺一 fail" in text, "E/V/A 证据包必须有缺项即失败的语义"


def test_depth_review_requires_numeric_eva_artifact_matrix():
    text = read_repo("skill/references/depth-review.md")
    required = (
        "E/V/A 证据链硬检查",
        "artifact",
        "命令/输出",
        "方向",
        "最终答案偏差",
        "多种子临界扫描",
        "有限尺寸/胞元形状",
        "阈值灵敏度系数",
        "全前沿价格灵敏度",
        "病态切换",
        "结构反推",
    )
    missing = [marker for marker in required if marker not in text]
    assert not missing, f"depth-review.md 缺少 E/V/A 检查项: {missing}"
    assert "缺少工件或数字 = FAIL" in text


def test_paper_and_runtime_keep_fragments_are_explicit():
    skill = read_repo("skill/SKILL.md")
    paper = read_repo("skill/references/paper-latex.md")
    templates = "\n".join(
        read_repo(path)
        for path in (
            "skill/assets/paper/main.tex",
            "skill/assets/paper/00-摘要.tex",
            "skill/assets/paper/05-模型的建立与求解.tex",
            "skill/assets/paper/06-模型检验.tex",
            "skill/assets/paper/07-模型评价.tex",
        )
    )
    required = (
        "model_identity",
        "逐问结果 JSON",
        "checks 字段",
        "聚合校验",
        "合同先行",
        "现象—原因—意义",
        "缺陷—影响—改进",
        "评委看见什么",
        "宏携带证书元数据",
        "reproduce.py",
    )
    missing = [marker for marker in required if marker not in skill + paper + templates]
    assert not missing, f"keep_fragments 合同缺失: {missing}"
    assert os.path.isfile(os.path.join(ROOT, "skill", "assets", "reproduce.py"))


def test_page_gate_appendix_label_matches_reusable_template():
    skill = read_repo("skill/SKILL.md")
    paper = read_repo("skill/references/paper-latex.md")
    appendix = read_repo("skill/assets/paper/11-附录.tex")
    assert "--appendix-label sec:appendix" in skill + paper
    assert "\\label{sec:appendix}" in appendix


def test_computation_standards_cover_six_pending_lessons():
    text = read_repo("skill/references/computation-standards.md")
    required = (
        "内部-内部最近点对",
        "max(min₂−max₁, min₁−max₂)",
        "nfirst > 0",
        "网格与成本文件的单位头",
        "按**粒子数**计算",
        "证明候选对集合一致",
        "块上限",
        "原子落盘",
        "恢复扫描",
    )
    missing = [marker for marker in required if marker not in text]
    assert not missing, f"computation-standards.md 未完整覆盖 L4/L5/L6/L7/L10/L11: {missing}"


def test_ledger_emits_certificate_metadata_macros():
    """数字宏必须能把证书的 n/seed/下界/状态带进论文。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = {
            "qX": {
                "value": 0.901,
                "unit": "1",
                "display": "90.10%",
                "role": "authoritative",
                "scenario_id": "QX-critical-primary",
                "status": "frozen",
                "source": {"script": "solve.py", "params": "n=40000",
                           "file": "result.json", "field": "p_hat"},
                "certificate": {
                    "family": "wilson_lower_95", "bound": 0.9002,
                    "threshold": 0.90, "n": 40000, "seed": 20260905,
                    "verdict": "feasible", "resolved": True,
                    "delta": 0.005, "u": 0.0008,
                },
            }
        }
        src = os.path.join(tmp, "ledger.json")
        out = os.path.join(tmp, "numbers.tex")
        io.open(src, "w", encoding="utf-8").write(json.dumps(ledger))
        code, _, err = run("ledger.py", "--emit-tex", src, "-o", out)
        assert code == 0, err
        tex = io.open(out, encoding="utf-8").read()
        for macro in ("\\qXBound", "\\qXN", "\\qXSeed", "\\qXVerdict",
                      "\\qXResolved", "\\qXDelta", "\\qXU", "\\qXCert"):
            assert macro in tex, f"缺证书宏 {macro}: {tex}"
        assert "seed=20260905" in tex and "已分辨" in tex


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
