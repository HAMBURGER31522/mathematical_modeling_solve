# -*- coding: utf-8 -*-
"""官方脚本的契约测试。

为什么必须有这个文件
--------------------
SKILL.md 里写着「官方脚本不可替代」——但一份独立 CR 指出：
这些脚本并没有兑现自己文档里承诺的行为（`certify.py` 在真实临界点上不输出三态 JSON、
`figqa.py` 不展开 `\\input` 导致对分节论文全面误判）。
**在契约测试通过之前，"官方、不可替代"是虚假确定性。**

跑法：
    python -m pytest scripts/tests/test_contracts.py -q
    （无 pytest 时：python scripts/tests/test_contracts.py）
"""
from __future__ import annotations

import io
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
PY = sys.executable
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


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


def test_openconf_reads_all_opening_configuration_keys():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    openconf = importlib.import_module("openconf")
    config = openconf.load_all()
    assert set(config) == {
        "赛事", "正文页数上限", "总页数下限", "图总数下限", "正文引用图下限",
        "摘要页数", "论文模板", "目标图样例目录", "总时限", "主计算机时上限", "本机核数",
    }
    assert config["总页数下限"].startswith("<必填:")


def test_gate_defaults_come_from_opening_configuration():
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    openconf = importlib.import_module("openconf")
    latex_gate = importlib.import_module("latex_gate")
    figqa = importlib.import_module("figqa")
    original_path = openconf.CONFIG_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "开题.md")
            config.write_text(
                "总页数下限: 60\n正文页数上限: 10\n图总数下限: 0\n正文引用图下限: 0\n",
                encoding="utf-8",
            )
            openconf.CONFIG_PATH = config
            log = _fake_log(tmp, pages=53)
            assert latex_gate.main([log]) == 1
            assert latex_gate.main([log, "--min-pages", "50"]) == 0
            figdir = os.path.join(tmp, "图")
            os.makedirs(figdir)
            assert figqa.main([
                figdir,
                "--out", os.path.join(tmp, "figqa.json"),
                "--contact", os.path.join(tmp, "contact.png"),
            ]) == 0

            config.write_text("正文页数上限: 10\n", encoding="utf-8")
            try:
                latex_gate.main([log])
            except SystemExit as exc:
                assert str(exc) == "请在 开题.md 填写 总页数下限"
            else:
                raise AssertionError("缺少配置必须中止，不能回退到旧默认值")
    finally:
        openconf.CONFIG_PATH = original_path


def test_gate_help_omits_legacy_numeric_defaults():
    for script, legacy_default in (
        ("latex_gate.py", ("默认 40", "默认 20")),
        ("figqa.py", ("默认 12", "默认 8")),
    ):
        code, out, err = run(script, "--help")
        assert code == 0, err
        text = out + err
        assert not any(value in text for value in legacy_default), text


def test_openconf_rejects_placeholders_and_requires_usable_sample_images():
    """示例配置不是已配置；图样例目录必须是实际可读的图片目录。"""
    code, out, err = run("openconf.py")
    assert code == 1 and "正文页数上限" in out + err, "根配置的 <必填:...> 未被拒绝"

    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    openconf = importlib.import_module("openconf")
    original_path = openconf.CONFIG_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp, "开题.md")
            image_dir = Path(tmp, "samples")
            image_dir.mkdir()
            config_path.write_text(
                "赛事: 测试赛\n正文页数上限: 20\n总页数下限: 40\n图总数下限: 12\n"
                "正文引用图下限: 8\n摘要页数: 1\n论文模板: 官方\n"
                f"目标图样例目录: {image_dir}\n总时限: 72h\n主计算机时上限: 20h\n本机核数: 32\n",
                encoding="utf-8",
            )
            openconf.CONFIG_PATH = config_path
            try:
                openconf.validate_opening_config(openconf.load_all())
            except ValueError as exc:
                assert "可读图片" in str(exc)
            else:
                raise AssertionError("空图目录未被拒绝")

            Path(image_dir, "sample.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            openconf.validate_opening_config(openconf.load_all())
    finally:
        openconf.CONFIG_PATH = original_path


TASK_CARD_FIELDS = (
    "objective", "input_data", "decision_variables", "constraints", "expected_outputs",
    "dependencies", "risks", "validation_requirements", "data_evidence",
)


def _task_cards_text(missing=None):
    lines = ["## 问题 1"]
    for field in TASK_CARD_FIELDS:
        if field != missing:
            lines.append(f"- {field}: 已填写")
    return "\n".join(lines) + "\n"


def test_task_cards_requires_all_fields_and_predates_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        cards = os.path.join(tmp, "拆问卡.md")
        ledger = os.path.join(tmp, "results_ledger.json")
        io.open(cards, "w", encoding="utf-8").write(_task_cards_text())
        os.utime(cards, (1_600_000_000, 1_600_000_000))
        io.open(ledger, "w", encoding="utf-8").write("{}")
        code, out, err = run("task_cards.py", "--cards", cards, "--ledger", ledger)
        assert code == 0, out + err

        io.open(cards, "w", encoding="utf-8").write(
            _task_cards_text(missing="validation_requirements")
        )
        code, out, _ = run("task_cards.py", "--cards", cards, "--ledger", ledger)
        assert code != 0 and "validation_requirements" in out

        io.open(cards, "w", encoding="utf-8").write(_task_cards_text())
        os.utime(cards, (2_000_000_000, 2_000_000_000))
        code, out, _ = run("task_cards.py", "--cards", cards, "--ledger", ledger)
        assert code != 0 and "早于" in out


def _pilot_payload():
    split = {"train_ids": ["A", "B"], "test_ids": ["C"]}
    return {
        "protocol": {
            "questions": {
                "ques1": {
                    "budget_seconds": 30,
                    "candidates": [{"name": "基线"}, {"name": "候选模型"}],
                },
            },
        },
        "questions": {
            "ques1": {
                "candidates": [
                    {"name": "基线", "is_baseline": True, "data_split": split,
                     "metric_name": "MAE", "seconds": 5, "ran_ok": True},
                    {"name": "候选模型", "is_baseline": False, "data_split": split,
                     "metric_name": "MAE", "seconds": 12, "ran_ok": False,
                     "failure": "数值求解未收敛"},
                ],
            },
        },
    }


def test_pilot_gate_requires_shared_split_current_protocol_and_real_run():
    with tempfile.TemporaryDirectory() as tmp:
        result_path = os.path.join(tmp, "pilot_results.json")
        payload = _pilot_payload()
        io.open(result_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
        code, out, err = run("pilot_gate.py", "--results", result_path)
        assert code == 0, out + err

        bad_split = json.loads(json.dumps(payload, ensure_ascii=False))
        bad_split["questions"]["ques1"]["candidates"][1]["data_split"] = {"train_ids": ["A"], "test_ids": ["B", "C"]}
        io.open(result_path, "w", encoding="utf-8").write(json.dumps(bad_split, ensure_ascii=False))
        code, out, _ = run("pilot_gate.py", "--results", result_path)
        assert code != 0 and "数据划分" in out

        stale = json.loads(json.dumps(payload, ensure_ascii=False))
        stale["questions"]["ques1"]["candidates"][1]["name"] = "上一轮模型"
        io.open(result_path, "w", encoding="utf-8").write(json.dumps(stale, ensure_ascii=False))
        code, out, _ = run("pilot_gate.py", "--results", result_path)
        assert code != 0 and "协议" in out

        no_success = json.loads(json.dumps(payload, ensure_ascii=False))
        for candidate in no_success["questions"]["ques1"]["candidates"]:
            candidate["ran_ok"] = False
        io.open(result_path, "w", encoding="utf-8").write(json.dumps(no_success, ensure_ascii=False))
        code, out, _ = run("pilot_gate.py", "--results", result_path)
        assert code != 0 and "真实跑通" in out


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
        _, out, _ = run("figqa.py", "--min-figures", "1", "--min-body-figures", "0", os.path.join(tmp, "图"),
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
        run("figqa.py", "--min-figures", "1", "--min-body-figures", "0", os.path.join(tmp, "图"), "--tex", os.path.join(tmp, "论文", "main.tex"),
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
            "--min-figures", "12", "--min-body-figures", "0", "--draft")
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
        rc, out, _ = run("latex_gate.py", log, "--min-pages", "40", "--max-body-pages", "20")
        assert rc == 1, "页数不足必须退出码 1"
        assert "总页数 25" in out, out[:300]


def test_latex_gate_unknown_page_count_is_blocking():
    """核不到页数就不能算通过——否则地板被静默跳过（实测踩过）。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=None)
        rc, out, _ = run("latex_gate.py", log, "--min-pages", "40", "--max-body-pages", "20")
        assert rc == 1, "页数取不到必须判 FAIL 而不是 PASS"
        assert "页数无法判定" in out, out[:300]


def test_latex_gate_passes_thick_paper():
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=53)
        rc, _, _ = run("latex_gate.py", log, "--min-pages", "40", "--max-body-pages", "20")
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


def _make_reproduce_package(tmp, with_runtime=True):
    import shutil
    shutil.copyfile(os.path.join(ROOT, "assets", "reproduce.py"),
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


def test_paper_and_runtime_keep_fragments_are_explicit():
    """写作合同必须落在任务路径上（v3.3：运行时 JSON 链已废除，改由 ledger 单链承担）。"""
    workflow = read_repo("workflows/solve-full.md")
    figure = read_repo("references/figure-style.md")
    templates = chr(10).join(
        read_repo(path)
        for path in (
            "assets/paper/main.tex",
            "assets/paper/0.摘要.tex",
            "assets/paper/6.模型检验.tex",
            "assets/paper/7.模型评价.tex",
            "assets/paper/10.附录.tex",
        )
    )
    corpus = workflow + figure + templates
    required = (
        "现象—原因—意义",      # 每张正文图后的解读段
        "缺陷—影响—改进",      # 模型评价章的缺点写法
        "评委看见什么",          # 画图前先写目的
        "证书元数据",            # 宏必须把 n/seed/下界/状态带进论文
        "[NUMBERS-MISSING]",     # 宏未注入时显式失败，不静默
        "abstract:end",          # 摘要一页由 .aux 程序化核验
    )
    missing = [marker for marker in required if marker not in corpus]
    assert not missing, "写作合同缺失（未落在任务路径上）: %s" % missing


def test_validation_chapter_keeps_six_subsections():
    """独立检验章六小节是对标人工基线量出的最大单项缺口，不得被通用模板冲掉。"""
    text = read_repo("assets/paper/6.模型检验.tex")
    for marker in ("双路互证", "可核事实", "参数灵敏度", "样本量与收敛", "稳健性", "适用边界"):
        assert marker in text, "模型检验章缺小节: %s" % marker


def test_page_gate_appendix_label_matches_reusable_template():
    """正文页数与附录页数靠 sec:appendix 切分：模板里要有这个 label，工作流里要真的传这个参数。"""
    workflow = read_repo("workflows/solve-full.md")
    appendix = read_repo("assets/paper/10.附录.tex")
    assert "--appendix-label sec:appendix" in workflow
    assert chr(92) + "label{sec:appendix}" in appendix


def test_general_execution_lessons_survive_in_gotchas():
    """长批可恢复性等通用教训必须仍在任务路径上；渗流题专有的降级为带触发条件的条目。"""
    gotchas = read_repo("references/gotchas.md")
    rules = read_repo("rules/execution-discipline.md")
    corpus = gotchas + rules
    for marker in ("分块", "原子", "恢复扫描", "语义主键", "实测"):
        assert marker in corpus, "通用执行纪律丢失: %s" % marker
    # 题目专有内容只能出现在带触发条件的条目里，不得成为通用红线
    redlines = read_repo("rules/modeling-redlines.md")
    for banned in ("Balberg", "细长胞元", "粒子数"):
        assert banned not in redlines, "题目专有名词回流到通用红线: %s" % banned
    assert "随机几何" in gotchas, "渗流类触发条件条目丢失"


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


def test_batch_gate_separates_resumable_from_all_or_nothing():
    """一次性 pool.map 必须判 FAIL，分块+原子落盘+续跑扫描必须判 PASS。"""
    allornothing = (
        "from multiprocessing import Pool" + chr(10) +
        "with Pool(14) as pool:" + chr(10) +
        "    res = pool.map(one, jobs)" + chr(10) +
        "open('out.csv','w').write(str(res))" + chr(10)
    )
    resumable = (
        "import os, glob" + chr(10) +
        "from multiprocessing import Pool" + chr(10) +
        "done = set(os.listdir('chunks'))" + chr(10) +
        "with Pool(14) as pool:" + chr(10) +
        "    res = pool.map(one, jobs)" + chr(10) +
        "open('t.tmp','w').write(str(res))" + chr(10) +
        "os.replace('t.tmp', 'chunks/c1.csv')" + chr(10)
    )
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.py")
        good = os.path.join(tmp, "good.py")
        io.open(bad, "w", encoding="utf-8").write(allornothing)
        io.open(good, "w", encoding="utf-8").write(resumable)
        gate = os.path.join(ROOT, "scripts", "batch_gate.py")
        out = os.path.join(tmp, "report.md")

        r = subprocess.run([PY, gate, bad, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "一次性 pool.map 未被判 FAIL"

        r = subprocess.run([PY, gate, good, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

        # 空检查一律记 fail，不得因“没发现问题”而通过
        r = subprocess.run([PY, gate, os.path.join(tmp, "nothing_*.py"), "--out", out],
                           capture_output=True, env=ENV)
        assert r.returncode == 1, "空匹配未记 fail"

        # 豁免必须带理由
        r = subprocess.run([PY, gate, bad, "--skip", "bad.py=", "--out", out],
                           capture_output=True, env=ENV)
        assert r.returncode == 2, "空理由的豁免未被拒绝"


def _make_skill_fixture(root, body_lines=10, routes=None, fallback=True):
    """造一个最小合法 skill 目录，供 skill_smoke 的失败路径测试用。"""
    os.makedirs(os.path.join(root, "workflows"), exist_ok=True)
    os.makedirs(os.path.join(root, "references"), exist_ok=True)
    desc = ("---" + chr(10) + "name: t" + chr(10) +
            "description: 当用户要求" + chr(34) + "求解数学建模竞赛题" + chr(34) +
            "或" + chr(34) + "写数模论文" + chr(34) +
            "时使用，覆盖读题到论文的端到端交付，包含数据体检与门禁。" + chr(10) +
            "---" + chr(10))
    body = "# t" + chr(10) + "## Known Gotchas" + chr(10) + ("x" + chr(10)) * body_lines
    io.open(os.path.join(root, "SKILL.md"), "w", encoding="utf-8").write(desc + body)
    routes = routes if routes is not None else ["solve"]
    lines = ["tasks:"]
    for r in routes:
        lines += ["  - id: " + r, "    workflow: workflows/" + r + ".md"]
        io.open(os.path.join(root, "workflows", r + ".md"), "w", encoding="utf-8").write("x")
    if fallback:
        lines += ["  - id: other", "    workflow: workflows/other.md"]
        io.open(os.path.join(root, "workflows", "other.md"), "w", encoding="utf-8").write("x")
    io.open(os.path.join(root, "routing.yaml"), "w", encoding="utf-8").write(chr(10).join(lines))


def test_skill_smoke_catches_forgetting_errors():
    """自检脚本必须能判死超预算、断链路由和缺兜底；本仓自身必须是绿的。"""
    gate = os.path.join(ROOT, "scripts", "skill_smoke.py")
    r = subprocess.run([PY, gate, "--root", ROOT], capture_output=True, env=ENV)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

    with tempfile.TemporaryDirectory() as tmp:
        ok = os.path.join(tmp, "ok")
        _make_skill_fixture(ok)
        r = subprocess.run([PY, gate, "--root", ok], capture_output=True, env=ENV)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

        fat = os.path.join(tmp, "fat")
        _make_skill_fixture(fat, body_lines=200)
        r = subprocess.run([PY, gate, "--root", fat], capture_output=True, env=ENV)
        assert r.returncode == 1, "SKILL.md 正文超 90 行未被判死"

        nofall = os.path.join(tmp, "nofall")
        _make_skill_fixture(nofall, fallback=False)
        r = subprocess.run([PY, gate, "--root", nofall], capture_output=True, env=ENV)
        assert r.returncode == 1, "缺 other 兜底行未被判死"

        broken = os.path.join(tmp, "broken")
        _make_skill_fixture(broken)
        io.open(os.path.join(broken, "routing.yaml"), "a", encoding="utf-8").write(
            chr(10) + "  - id: ghost" + chr(10) + "    workflow: workflows/ghost.md" + chr(10))
        r = subprocess.run([PY, gate, "--root", broken], capture_output=True, env=ENV)
        assert r.returncode == 1, "routing 指向不存在的 workflow 未被判死"

        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        r = subprocess.run([PY, gate, "--root", empty], capture_output=True, env=ENV)
        assert r.returncode == 1, "缺 SKILL.md 未被判死"


def test_refs_check_rejects_unverifiable_citations():
    """无 DOI、空条目一律记 fail；离线只做结构检查；文件不存在是用法错误。"""
    gate = os.path.join(ROOT, "scripts", "refs_check.py")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "r.md")

        nodoi = os.path.join(tmp, "nodoi.bib")
        io.open(nodoi, "w", encoding="utf-8").write(
            "@article{a," + chr(10) + "  title = {Some Paper}," + chr(10) +
            "  year = {2024}" + chr(10) + "}" + chr(10))
        r = subprocess.run([PY, gate, nodoi, "--out", out, "--offline"],
                           capture_output=True, env=ENV)
        assert r.returncode == 1, "无 DOI 的条目未被判 FAIL"

        withdoi = os.path.join(tmp, "ok.bib")
        io.open(withdoi, "w", encoding="utf-8").write(
            "@article{b," + chr(10) + "  title = {Some Paper}," + chr(10) +
            "  doi = {10.1038/s41586-024-07780-8}" + chr(10) + "}" + chr(10))
        r = subprocess.run([PY, gate, withdoi, "--out", out, "--offline"],
                           capture_output=True, env=ENV)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

        blank = os.path.join(tmp, "blank.bib")
        io.open(blank, "w", encoding="utf-8").write("")
        r = subprocess.run([PY, gate, blank, "--out", out, "--offline"],
                           capture_output=True, env=ENV)
        assert r.returncode == 1, "空条目未记 fail（不得因没发现问题而通过）"

        r = subprocess.run([PY, gate, os.path.join(tmp, "ghost.bib"), "--out", out],
                           capture_output=True, env=ENV)
        assert r.returncode == 2, "文件不存在应判用法错误"



def test_seed_gate_catches_answer_drift_across_seed_families():
    """答案随独立种子族漂移即为未分辨；单族、缺相邻档同样判死。"""
    gate = os.path.join(ROOT, "scripts", "seed_gate.py")

    def spec(fams):
        return {"question": "Q", "answer": 615, "direction": "min",
                "threshold": 0.90, "alpha": 0.05, "families": fams}

    stable = {str(f): {"614": {"k": 17950 + f, "n": 20000},
                       "615": {"k": 18150 + f, "n": 20000}} for f in (1, 2, 3)}
    drift = dict(stable)
    drift["1"] = {"614": {"k": 18200, "n": 20000}, "615": {"k": 18260, "n": 20000}}

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "g.md")

        def run(payload):
            path = os.path.join(tmp, "s.json")
            io.open(path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
            return subprocess.run([PY, gate, path, "--out", out],
                                  capture_output=True, env=ENV).returncode

        assert run(spec(stable)) == 0, "三族一致却未判 PASS"
        assert run(spec(drift)) == 1, "某族答案漂移未被判死"
        assert run(spec({"1": stable["1"]})) == 1, "单种子族未被判死"
        assert run(spec({str(f): {"615": stable[str(f)]["615"]} for f in (1, 2, 3)})) == 1,             "缺相邻档（夹逼不成立）未被判死"

        bad = os.path.join(tmp, "bad.json")
        io.open(bad, "w", encoding="utf-8").write("{}")
        r = subprocess.run([PY, gate, bad, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 2, "输入结构不合法应判用法错误"


def test_skill_smoke_guards_thin_shell_and_placeholders():
    """薄壳承重结构与指令目录占位符必须被机器守住，不能靠人记得。"""
    gate = os.path.join(ROOT, "scripts", "skill_smoke.py")

    def run(root):
        return subprocess.run([PY, gate, "--root", root], capture_output=True, env=ENV)

    assert run(ROOT).returncode == 0, run(ROOT).stdout.decode("utf-8", "replace")

    with tempfile.TemporaryDirectory() as tmp:
        import shutil
        for case, mutate in (
            ("no_xml", lambda p: _sub(p, "CLAUDE.md", "<task-routing>", "")),
            ("no_autotrigger", lambda p: _sub(p, "CLAUDE.md", "## Auto-Triggers", "## Notes")),
            ("shell_route_drift", lambda p: _sub(p, "CLAUDE.md",
                                                 "`workflows/latex-fix.md`", "`workflows/ghost.md`")),
            ("fill_left", lambda p: _append(p, "workflows/task-execution.md",
                                            chr(10) + "<!-- FILL: 待补 -->" + chr(10))),
        ):
            root = os.path.join(tmp, case)
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "assets", "*.pyc"))
            mutate(root)
            assert run(root).returncode == 1, "%s 未被自检判死" % case


def _sub(root, rel, old, new):
    path = os.path.join(root, rel)
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))


def _append(root, rel, extra):
    path = os.path.join(root, rel)
    io.open(path, "a", encoding="utf-8").write(extra)


def test_every_gotcha_is_reachable_from_the_task_path():
    """激活优于存储：坑点只躺在 references/ 里不算捕获。

    判据来自「如何写一个好的skill」2.5——高代价陷阱必须同时被存储与激活，
    判断方法是「下次 Agent 走正常任务路径时，会自然读到这条经验吗」。
    任务路径 = SKILL.md 的 Known Gotchas、rules/、workflows/。
    """
    import re

    gotchas = read_repo("references/gotchas.md")
    headings = re.findall(r"^##\s+(.+?)\s*$", gotchas, re.M)
    assert headings, "gotchas.md 没有任何 ## 条目"

    task_path = read_repo("SKILL.md")
    for sub in ("rules", "workflows"):
        base = os.path.join(ROOT, sub)
        for name in sorted(os.listdir(base)):
            if name.endswith(".md"):
                task_path += read_repo(sub + "/" + name)

    def anchor(text):
        slug = text.lower().replace(" ", "-")
        return "".join(ch for ch in slug if ch.isalnum() or ch in "-_")

    orphans = [h for h in headings
               if anchor(h) not in task_path and h not in task_path]
    assert not orphans, "以下坑点只存不激活（任务路径上读不到）: %s" % orphans


def test_reference_check_resolves_anchors_not_just_files():
    """带 #锚点 的引用：文件要存在，锚点也要真的存在——悬空锚点是真实失败模式。"""
    import shutil

    gate = os.path.join(ROOT, "scripts", "skill_smoke.py")
    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, "good")
        shutil.copytree(ROOT, good, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "fonts", "*.pyc",
            "*.log", "*.aux", "*.pdf", "*.out", "*.toc", "*.xdv"))
        r = subprocess.run([PY, gate, "--root", good], capture_output=True, env=ENV)
        assert r.returncode == 0, ("真实锚点被误判为失效引用: "
                                   + r.stdout.decode("utf-8", "replace"))

        bad = os.path.join(tmp, "bad")
        shutil.copytree(ROOT, bad, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "fonts", "*.pyc",
            "*.log", "*.aux", "*.pdf", "*.out", "*.toc", "*.xdv"))
        path = os.path.join(bad, "workflows", "task-execution.md")
        io.open(path, "a", encoding="utf-8").write(
            chr(10) + "见 `references/gotchas.md#no-such-anchor-here`。" + chr(10))
        r = subprocess.run([PY, gate, "--root", bad], capture_output=True, env=ENV)
        assert r.returncode == 1, "悬空锚点未被判死"


def test_paper_template_matches_authoritative_mrite_layout():
    """对照 i3by4t3oyt/Mrite 高教社杯权威模板：算法表加宽首列、预处理表等宽、无死状态。"""
    import re

    tex = read_repo("assets/paper/5.1.1.分析与准备.tex")
    blocks = re.split(re.escape(chr(92) + "caption{"), tex)
    prep = next((b for b in blocks if b.startswith("数据预处理前后统计量对比")), "")
    algo = next((b for b in blocks if b.startswith("算法能力对比")), "")
    assert prep and algo, "5.1.1 缺预处理表或算法对比表"

    pattern = re.compile(r"tabularx\}\{" + re.escape(chr(92)) + r"textwidth\}\{(.+)\}")
    prep_cols = pattern.search(prep)
    algo_cols = pattern.search(algo)
    assert prep_cols and algo_cols, "两张表都要用 tabularx"
    assert "hsize" not in prep_cols.group(1), "预处理表应等宽（权威版是 CCCCC），不该加权重"
    assert "hsize=2.5" in algo_cols.group(1), "算法对比表首列要加宽——算法名比等级长得多"
    assert "centering" in algo_cols.group(1), "权威版漏了 centering，我方按 Mrite 自己的规范补齐"

    main = read_repo("assets/paper/main.tex")
    if chr(92) + "title{" in main:
        assert chr(92) + "maketitle" in main, "声明了 title 却从不 maketitle —— 死状态，应删除"


def test_figure_style_covers_authoritative_plotting_rules():
    """权威源 CLAUDE.md「三、代码规范」里可迁移的条目必须落在图式卡上。"""
    style = read_repo("references/figure-style.md")
    for token, why in (
        ("imshow", "热图的 matplotlib 等价做法"),
        ("colorbar", "热图必须带色标"),
        ("PingFang", "跨平台中文字体栈（macOS）"),
        ("Hiragino", "跨平台中文字体栈（macOS）"),
        ("Microsoft YaHei", "跨平台中文字体栈（Windows）"),
        ("DejaVu", "字体栈末级 fallback"),
        ("豆腐块", "缺字返工检验"),
    ):
        assert token in style, "figure-style.md 缺 %s（%s）" % (token, why)


def test_every_shipped_gate_is_invoked_on_the_task_path():
    """发了门禁却没有任何流程调用它 = 死内容。

    实测：certify.py 是三态证书的执行体、R2 要求结论必须带证书，
    但 workflows 与 rules 里从未出现过这条命令——门禁在盘上，没人跑。
    这与「坑点只存不激活」是同一个病，只是对象换成了脚本。
    """
    task_path = read_repo("SKILL.md")
    for sub in ("rules", "workflows"):
        base = os.path.join(ROOT, sub)
        for name in sorted(os.listdir(base)):
            if name.endswith(".md"):
                task_path += read_repo(sub + "/" + name)

    helpers = {"openconf.py", "ledger.py",  # 被别的脚本调用，或以子命令形式出现
               "skill_smoke.py"}        # 审 skill 自身，由本契约测试调用，不在解题路径上
    orphans = []
    for name in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
        if not name.endswith(".py") or name in helpers:
            continue
        if name not in task_path:
            orphans.append(name)
    assert not orphans, "以下门禁没有任何流程调用（发了没人跑）: %s" % orphans


def test_official_gates_are_not_bypassed_by_ad_hoc_commands():
    """流程里不得用裸命令替代已有门禁——这正是我方红线禁止的自写替代品。"""
    for rel in ("workflows/solve-full.md", "workflows/paper-only.md",
                "workflows/latex-fix.md", "workflows/gate-triage.md",
                "workflows/task-execution.md"):
        text = read_repo(rel)
        assert "api.crossref.org" not in text, (
            rel + " 用裸 curl 查 Crossref，绕过了 refs_check.py 的标题比对与退出码")


def test_attribution_states_verified_facts():
    """已发布仓库里的来源声明必须与实际一致——写错的许可与来源比不写更糟。"""
    import json

    text = read_repo("ATTRIBUTION.md")
    assert "i3by4t3oyt/Mrite" in text, "论文模板的真实来源是 i3by4t3oyt/Mrite"
    assert "Rzna-5559" not in text, "旧源 Rzna-5559/Mrite 并非我方所用，不应出现在来源声明里"
    assert "仓库无 LICENSE 文件" not in text, "权威源是带 LICENSE 的，该断言已过期"

    cards = json.loads(read_repo("references/method-cards.json"))
    count = sum(len(sub["methods"]) for domain in cards for sub in domain["subdomains"])
    assert str(count) in text, "ATTRIBUTION 写的方法数与 method-cards.json 实际 %d 个不符" % count


def test_published_skill_carries_no_lab_narrative():
    """文章 2.12：会话历史、评审过程、实验轮次是项目叙事，不是可复用知识。

    它们留在 skill 里有两个后果：真实任务会读到已过期的决策，
    以及公开仓库暴露本机目录结构。二者都属于「记录位置放错层」。
    """
    banned = {
        "初稿": "评审阶段标记",
        "待拍板": "评审阶段标记",
        "v0.2": "内部版本号",
        "落地顺序": "迁移计划，属实验室",
        "loop2-r2": "实验轮次标识",
        "loop3-r1": "实验轮次标识",
        "STATUS.md": "实验室运行态文件",
        "spec.md": "实验室契约文件",
        chr(70) + ":" + chr(92): "本机绝对路径（Windows）",
        chr(70) + ":/": "本机绝对路径（正斜杠）",
    }
    # 放行检测器自身：它的职责就是识别这些模式，文档里说明自己检测什么不算泄漏
    exempt = {"scripts/pkg_scan.py"}
    offenders = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "tests", "fonts")]
        for name in filenames:
            if not name.endswith((".md", ".yaml", ".py")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace(chr(92), "/")
            if rel in exempt:
                continue
            text = read_repo(rel) or ""
            for token, why in banned.items():
                if token in text:
                    offenders.append("%s 含 %r（%s）" % (rel, token, why))
    assert not offenders, "已发布的 skill 里残留实验室叙事:" + chr(10) + chr(10).join(offenders)


def test_routing_covers_partial_solve_without_paper():
    """比赛里常见「先做第一问」「只要模型和结果、暂时不写论文」，不能落到 other。

    other 走 task-execution，不保证 P0-P4 的拆问卡、Pilot、独立测试与冻结都发生；
    这类请求恰恰最需要那几道纪律。
    """
    routing = read_repo("routing.yaml")
    assert "solve-only" in routing, "缺 solve-only 路由：分阶段求解会落到 other 而丢失 P0-P4 纪律"
    assert os.path.isfile(os.path.join(ROOT, "workflows", "solve-only.md")), \
        "routing 声明了 solve-only 却没有对应 workflow"
    for phrase in ("先做", "不写论文"):
        assert phrase in routing, "solve-only 的 trigger_examples 需覆盖真实说法：%s" % phrase
    for shell in ("CLAUDE.md", "CODEX.md"):
        assert "solve-only" in read_repo(shell), shell + " 的 Quick Routing 未同步 solve-only"


def test_method_cards_have_a_query_entry_not_a_slurp():
    """1769 行的方法卡没有查询入口，P2 只会整文件读或截断——渐进加载名存实亡。"""
    assert os.path.isfile(os.path.join(ROOT, "scripts", "method_query.py")), \
        "method-cards.json 需要查询脚本，否则「按需读」无法执行"
    workflow = read_repo("workflows/solve-full.md")
    assert "method_query.py" in workflow, "P2 必须写出具体查询命令，而不是「按需读方法卡」"


def test_workflow_steps_stay_actionable():
    """单步塞太多等于没有分步：物理压行不减少认知负荷。"""
    over = []
    base = os.path.join(ROOT, "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith(".md"):
            continue
        for number, line in enumerate(read_repo("workflows/" + name).split(chr(10)), 1):
            if len(line) > 400:
                over.append("workflows/%s:%d 长 %d 字符" % (name, number, len(line)))
    assert not over, "以下步骤过载，应拆成子步骤:" + chr(10) + chr(10).join(over)


def test_always_read_is_universal_only():
    """Always Read 只放任何任务都适用的约束；领域规则由路由按需带。

    规范：永远一起加载的文件应合并或各自获得独立加载理由。
    纯 LaTeX 修错不该被迫读完建模红线。
    """
    import re

    skill = read_repo("SKILL.md")
    block = re.search(r"<!-- ALWAYS_READ_START -->(.*?)<!-- ALWAYS_READ_END -->", skill, re.S)
    assert block, "SKILL.md 缺 Always Read 标记块"
    entries = [ln for ln in block.group(1).split(chr(10)) if ln.strip().startswith(("1.", "2.", "3.", "-"))]
    assert len(entries) <= 1, \
        "Always Read 有 %d 条：领域规则应改由路由的 required_reads 按需带" % len(entries)

    routing = read_repo("routing.yaml")
    ids = re.findall(r"^\s*-\s*id:\s*(\S+)", routing, re.M)
    reads = re.findall(r"^\s*required_reads:", routing, re.M)
    assert len(reads) >= len(ids) - 1, \
        "每条路由都要写 required_reads（other 兜底可省），当前 %d 条路由只有 %d 条声明" % (
            len(ids), len(reads))


def test_no_baseline_problem_specifics_leak_into_the_skill():
    """举证可以留，基线题的答案数值与「同题」框架不能留。

    泛化规则：记录的内容必须脱离当前项目上下文也能看懂。
    「两族各判 614 与 615」对做别的题的人是噪音，还会让人以为这个 skill 是为那道题写的——
    与 Balberg、细长胞元属同一类。正确写法是「判出相邻但不同的档位」，
    保留「这件事真实发生过」而不带走题目。

    语料标签（[多波束][定日镜场][微构体] 等 12 篇获奖论文的简称）不在禁列：
    它们是统计结论的可核查出处，等同于引文，与「读者正在做哪道题」无关。
    """
    import re

    numeric = re.compile(r"(?<![0-9.])(614|615|616)(?![0-9.])")
    phrases = {
        "同题范文": "假设读者正在做同一道题",
        "同题基线": "同上",
        "华数杯": "基线赛事名",
    }
    allow = {"references/method-cards.json",
             # 它的职责就是检测这些模式，文档里描述自己检测什么不算泄漏
             "scripts/pkg_scan.py"}
    offenders = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "tests", "fonts")]
        for name in filenames:
            if not name.endswith((".md", ".py", ".yaml", ".tex")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace(chr(92), "/")
            if rel in allow:
                continue
            text = read_repo(rel) or ""
            for hit in set(numeric.findall(text)):
                offenders.append("%s 含基线答案档位 %s" % (rel, hit))
            for token, why in phrases.items():
                if token in text:
                    offenders.append("%s 含 %r（%s）" % (rel, token, why))
    assert not offenders, "基线题专有内容泄漏到通用 skill:" + chr(10) + chr(10).join(offenders)



ROLES = ("Coordinator", "Modeler", "Critic", "Coder",
         "Illustrator", "Writer", "Auditor", "Finisher")


def test_solve_workflow_starts_with_a_spec_gate():
    """SDD：PRD 先行，且在「打磨完成」之前不得进入任何实现动作。

    对应 Trellis-Herbivore 的硬门禁——brainstorm → grill-me 完成之前，
    禁止策略决策、禁止写实现文档、禁止 start。我方等价物：
    PRD 未过打磨关，不得进 P0 之后的任何阶段。
    """
    text = read_repo("workflows/solve-full.md")
    assert "PRD" in text, "工作流缺规格阶段（PRD）"
    assert "打磨" in text or "grill" in text.lower(), "PRD 之后缺打磨关"
    assert "P-1" in text or "规格" in text.split("## P0")[0], "规格阶段必须排在 P0 之前"
    head = text.split("## P0")[0]
    assert "不得" in head or "禁止" in head, "规格关必须写明未过关之前不许做什么"


def test_workflow_names_the_role_handoffs():
    """每个阶段要写清是谁在做、交出什么——交接点没有产物就是口头传话。"""
    text = read_repo("workflows/solve-full.md")
    missing = [r for r in ROLES if r not in text]
    assert not missing, "工作流未标注角色: %s" % missing


def test_workflow_stays_model_agnostic():
    """工作流只写角色，不写模型名——换模型不该让流程失效。

    模型分配属环境配置，落在 开题.md；写进工作流就等于把某一套账号钉死在通用 skill 里。
    按词边界匹配：solve 里的 sol、personal 里的 sona 之类不算命中。
    """
    import re

    pattern = re.compile(
        r"(?<![A-Za-z])(Opus|opus|Codex|codex|Claude|GPT|sol|astra|terra|luna)(?![A-Za-z])")
    offenders = []
    for name in sorted(os.listdir(os.path.join(ROOT, "workflows"))):
        if not name.endswith(".md"):
            continue
        text = read_repo("workflows/" + name)
        for hit in sorted(set(pattern.findall(text))):
            offenders.append("workflows/%s 含模型名 %r" % (name, hit))
    assert not offenders, "工作流里出现模型名（应移到 开题.md）:" + chr(10) + chr(10).join(offenders)



def test_opening_config_carries_the_role_assignment():
    """角色→模型的映射是可改配置，必须在 开题.md 里，且覆盖全部角色。"""
    text = read_repo("开题.md")
    assert "角色" in text, "开题.md 缺角色分配段"
    missing = [r for r in ROLES if r not in text]
    assert not missing, "开题.md 的角色分配缺: %s" % missing


def test_readme_counts_match_the_repository():
    """README 写的脚本数、路由数、方法卡数、契约测试数必须与实测一致。

    这类数字改一次代码就可能失效，而读者没有任何办法察觉——
    「52 项全过」在本仓真实地过期过一次。
    """
    import json
    import re

    readme = read_repo("README.md")

    scripts = len([n for n in os.listdir(os.path.join(ROOT, "scripts")) if n.endswith(".py")])
    assert re.search(r"脚本从 10 个加到 \*\*%d 个\*\*" % scripts, readme), \
        "README 的脚本数与实际 %d 个不符" % scripts
    assert "scripts/        %d 个执行体" % scripts in readme, \
        "架构图里的脚本数与实际 %d 个不符" % scripts

    routes = len(re.findall(r"^\s*-\s*id:", read_repo("routing.yaml"), re.M))
    assert "%d 条含 other 兜底" % routes in readme, "README 的路由数与实际 %d 条不符" % routes

    cards = json.loads(read_repo("references/method-cards.json"))
    methods = sum(len(s["methods"]) for d in cards for s in d["subdomains"])
    assert "%d 张方法卡" % methods in readme, "README 的方法卡数与实际 %d 张不符" % methods

    source = read_repo("scripts/tests/test_contracts.py")
    total = len(re.findall(r"^def (test_[A-Za-z0-9_]+)\(", source, re.M))
    assert "**%d 项全过**" % total in readme, \
        "README 的契约测试数与实际 %d 项不符" % total


def test_every_role_has_enumerated_dimensions():
    """角色不能只有一句话职责——每个角色要有可逐条对照的维度清单。

    单句职责在交接时无法验收：「Coder 负责实现」这种写法，交回来的东西
    是好是坏没有对照物。维度清单才是交接点的验收单。
    """
    import re

    doc = read_repo("references/roles.md")
    assert doc, "缺 references/roles.md"

    for role in ROLES:
        block = re.search(r"^##\s+%s\b(.*?)(?=^##\s|\Z)" % role, doc, re.S | re.M)
        assert block, "roles.md 缺角色 %s 的小节" % role
        body = block.group(1)
        items = re.findall(r"^\s*(?:\|\s*[A-Z]\d|\d+\.)\s", body, re.M)
        assert len(items) >= 5, "%s 的职责维度只有 %d 条，太笼统" % (role, len(items))


def test_auditor_covers_the_named_review_dimensions():
    """复核必须覆盖点名的三条，且不止这三条。"""
    import re

    doc = read_repo("references/roles.md")
    block = re.search(r"^##\s+Auditor\b(.*?)(?=^##\s|\Z)", doc, re.S | re.M)
    assert block, "roles.md 缺 Auditor 小节"
    body = block.group(1)
    for token, why in (
        ("最优解", "建模最优解有没有体现在文章里"),
        ("公式", "公式有没有写坏"),
        ("规范", "有没有按流程的规范文字写"),
    ):
        assert token in body, "Auditor 缺点名维度：%s" % why
    rows = re.findall(r"^\s*\|\s*A\d+\s*\|", body, re.M)
    assert len(rows) >= 8, "Auditor 只有 %d 条维度——点名的三条之外还有不少" % len(rows)


def test_roles_are_reachable_from_the_task_path():
    """角色清单要在任务路径上读得到，不能只躺在 references。"""
    corpus = read_repo("workflows/solve-full.md") + read_repo("开题.md")
    assert "references/roles.md" in corpus, "roles.md 未被任何任务路径引用"


def test_modeling_design_has_an_explicit_owner():
    """谁提出建模思路必须写死——否则它会掉在 Coordinator 与 Modeler 之间。

    Modeler 这个名字像原创者，但它的维度全是复核；若 Coordinator 也不认领，
    「先认题型、定主路线与核验路线」这件最要紧的事就没有主人。
    """
    import re

    doc = read_repo("references/roles.md")
    coord = re.search(r"^##\s+Coordinator\b(.*?)(?=^##\s)", doc, re.S | re.M).group(1)
    for token in ("题型", "主路线", "核验路线"):
        assert token in coord, "Coordinator 未认领建模思路：缺 %s" % token

    modeler = re.search(r"^##\s+Modeler\b(.*?)(?=^##\s)", doc, re.S | re.M).group(1)
    assert "不是原创" in modeler or "复核者" in modeler, \
        "Modeler 必须写明自己是复核者而非建模思路的原创者"


def test_critic_activates_stress_tests_and_anti_shallow():
    """审查会浅得过关——必须强制至少一种压力测试模型，并要求给证据位置。"""
    import re

    doc = read_repo("references/roles.md")
    critic = re.search(r"^##\s+Critic\b(.*?)(?=^##\s)", doc, re.S | re.M).group(1)
    for token, why in (
        ("Pre-Mortem", "预演失败"),
        ("Inversion", "反演：什么能保证失败"),
        ("证据位置", "反浅层：结论要能指到位置"),
    ):
        assert token in critic, "Critic 缺 %s（%s）" % (token, why)

    auditor = re.search(r"^##\s+Auditor\b(.*?)(?=^##\s|\Z)", doc, re.S | re.M).group(1)
    assert "证据位置" in auditor, "Auditor 的结论同样要能指到证据位置"


DESIGN_SECTIONS = ("题型判定", "形式化三要素", "主路线", "独立核验路线",
                   "承重假设", "口径", "证书预告", "分辨率", "数据接口", "已知失败模式")


def test_modeling_design_is_a_document_not_a_table_row():
    """建模详要是下游能否执行的前提——一行表格不够，必须成文并规定内容。

    执行方拿不到细节就只能自己重新推导，那就变成两方各建各的模型；
    对抗性审查也就无从谈起——它审的应当是已给出的思路，不是自己造一个。
    """
    doc = read_repo("references/roles.md")
    assert "建模详要" in doc, "roles.md 未定义建模详要这份产物"
    missing = [s for s in DESIGN_SECTIONS if s not in doc]
    assert not missing, "建模详要缺少必备内容: %s" % missing


def test_workflow_produces_the_modeling_design_before_execution():
    """建模详要必须在 P-1 产出、进入实现之前完成。"""
    text = read_repo("workflows/solve-full.md")
    head = text.split("## P0")[0]
    assert "建模详要" in head, "P-1 未产出建模详要"
    assert "design_gate.py" in text, "建模详要没有门禁，等于没写"


def test_design_gate_enforces_per_question_completeness():
    """门禁必须逐问检查十项内容，缺项判死；空匹配同样记 fail。"""
    gate = os.path.join(ROOT, "scripts", "design_gate.py")
    assert os.path.isfile(gate), "缺 scripts/design_gate.py"

    def make(tmp, name, body):
        path = os.path.join(tmp, name)
        io.open(path, "w", encoding="utf-8").write(body)
        return path

    full = "# 建模详要" + chr(10) + chr(10) + "## 问题一" + chr(10)
    for section in DESIGN_SECTIONS:
        full += "### " + section + chr(10) + "采用线性回归，令 $x=1$，足够下游据以执行。" + chr(10)

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "g.md")
        ok = make(tmp, "ok.md", full)
        r = subprocess.run([PY, gate, ok, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

        thin = make(tmp, "thin.md", full.replace("### 承重假设" + chr(10), ""))
        r = subprocess.run([PY, gate, thin, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "缺一项内容未被判死"

        empty = make(tmp, "empty.md",
                     full.replace("采用线性回归，令 $x=1$，足够下游据以执行。" + chr(10), "", 1))
        r = subprocess.run([PY, gate, empty, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "有标题无内容未被判死"

        none = make(tmp, "none.md", "# 建模详要" + chr(10) + "还没写。" + chr(10))
        r = subprocess.run([PY, gate, none, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "没有任何问题小节未被判死"


def test_design_gate_rejects_boilerplate_and_sections_without_concrete_subject():
    """长度达标的套话和无可指认具体物的散文都不能冒充建模详要。"""
    gate = os.path.join(ROOT, "scripts", "design_gate.py")

    def make(tmp, name, phrase):
        text = "# 建模详要\n\n## 问题一\n"
        for section in DESIGN_SECTIONS:
            text += "### " + section + "\n" + phrase + "\n"
        path = os.path.join(tmp, name)
        io.open(path, "w", encoding="utf-8").write(text)
        return path

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "g.md")
        boilerplate = make(tmp, "boilerplate.md", "本节内容将在后续讨论确定后补充完整并同步更新到本文档中。")
        r = subprocess.run([PY, gate, boilerplate, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "十节套话未被判空节"
        assert "空洞措辞" in r.stdout.decode("utf-8", "replace")

        vague = make(tmp, "vague.md", "我们会认真分析问题并综合考虑各种因素，从而得到合理可信的结论。")
        r = subprocess.run([PY, gate, vague, "--out", out], capture_output=True, env=ENV)
        assert r.returncode == 1, "没有可指认具体物的长段落未被判空节"
        assert "可指认的具体物" in r.stdout.decode("utf-8", "replace")


def test_pilot_gate_enforces_candidate_baseline_metric_budget_and_failure_records():
    """Pilot 必须保留可比较的完整证据，跑挂也不能从记录中消失。"""
    with tempfile.TemporaryDirectory() as tmp:
        result_path = os.path.join(tmp, "pilot_results.json")

        def check(payload, expected):
            io.open(result_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
            code, out, err = run("pilot_gate.py", "--results", result_path)
            assert code == 1 and expected in out, out + err

        one_candidate = _pilot_payload()
        one_candidate["questions"]["ques1"]["candidates"] = one_candidate["questions"]["ques1"]["candidates"][:1]
        check(one_candidate, "至少 2")

        no_baseline = _pilot_payload()
        no_baseline["questions"]["ques1"]["candidates"][0]["is_baseline"] = False
        check(no_baseline, "is_baseline")

        mixed_metric = _pilot_payload()
        mixed_metric["questions"]["ques1"]["candidates"][1]["metric_name"] = "RMSE"
        check(mixed_metric, "metric_name")

        over_budget = _pilot_payload()
        over_budget["questions"]["ques1"]["candidates"][1]["seconds"] = 31
        check(over_budget, "budget_seconds")

        hidden_failure = _pilot_payload()
        hidden_failure["questions"]["ques1"]["candidates"][1].pop("failure")
        check(hidden_failure, "failure")

        no_budget = _pilot_payload()
        no_budget["protocol"]["questions"]["ques1"].pop("budget_seconds")
        io.open(result_path, "w", encoding="utf-8").write(json.dumps(no_budget, ensure_ascii=False))
        code, out, err = run("pilot_gate.py", "--results", result_path)
        assert code == 0 and "时间预算未声明" in out, out + err


def test_latex_gate_blocks_missing_numbers_macro_injection():
    """numbers.tex 缺失留下的显式标记必须让编译门禁失败。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=53)
        with io.open(log, "a", encoding="utf-8") as fh:
            fh.write("[NUMBERS-MISSING] numbers.tex 未找到\n")
        code, out, err = run("latex_gate.py", log, "--min-pages", "40", "--max-body-pages", "20")
        assert code == 1, "[NUMBERS-MISSING] 不能随编译成功静默通过"
        assert "ledger.py --emit-tex" in out + err


def test_latex_gate_requires_abstract_label_and_declared_abstract_page_count():
    """摘要 label 缺失或落在错误页时，摘要一页承诺必须被阻断。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = _fake_log(tmp, pages=53)
        aux = os.path.join(tmp, "main.aux")
        io.open(aux, "w", encoding="utf-8").write("\\relax\n")
        args = (log, "--aux", aux, "--abstract-label", "abstract:end", "--min-pages", "40", "--max-body-pages", "20")
        code, out, err = run("latex_gate.py", *args)
        assert code == 1 and "abstract:end" in out + err, "缺摘要标签不能静默通过"

        io.open(aux, "w", encoding="utf-8").write("\\newlabel{abstract:end}{{}{2}}\n")
        code, out, err = run("latex_gate.py", *args)
        assert code == 1 and "摘要页数" in out + err, "摘要标签页与开题配置不一致未被阻断"

        io.open(aux, "w", encoding="utf-8").write("\\newlabel{abstract:end}{{}{1}}\n")
        code, out, err = run("latex_gate.py", *args)
        assert code == 0, out + err

    template = read_repo("assets/paper/0.摘要.tex")
    body = re.sub(r"(?m)^%.*$", "", template)
    assert "\\label{abstract:end}" in body, "abstract:end 不能只留在注释里"


def test_specialized_probability_gates_record_quantified_not_applicable_reasons():
    """非随机几何题必须显式 N/A，而非冒充通用门禁或静默跳过。"""
    with tempfile.TemporaryDirectory() as tmp:
        reason = "确定性线性规划：0 个随机个体，0 次 Bernoulli 试验"
        degenerate_report = os.path.join(tmp, "degenerate.json")
        code, out, err = run("degenerate.py", "--not-applicable", reason, "--out", degenerate_report)
        assert code == 0 and "N/A" in out + err, out + err
        record = json.load(io.open(degenerate_report, encoding="utf-8"))
        assert record["verdict"] == "N/A" and record["reason"] == reason

        sample_report = os.path.join(tmp, "sample.json")
        code, out, err = run("sample_gate.py", "--not-applicable", reason, "--report", sample_report)
        assert code == 0 and "N/A" in out + err, out + err
        record = json.load(io.open(sample_report, encoding="utf-8"))
        assert record["verdict"] == "N/A" and record["reason"] == reason

        for script, out_flag, report in (
            ("degenerate.py", "--out", degenerate_report),
            ("sample_gate.py", "--report", sample_report),
        ):
            code, _, _ = run(script, "--not-applicable", "", out_flag, report)
            assert code == 2, f"{script} 的空 N/A 理由必须是用法错误"
            code, _, _ = run(script, "--not-applicable", "不适用", out_flag, report)
            assert code == 2, f"{script} 的 N/A 理由必须量化"

    workflow = read_repo("workflows/solve-full.md")
    assert "题型/方法家族" in workflow and "N/A + 定量理由" in workflow
    assert "禁止手搓教科书算法" not in workflow
    assert "优先用有维护" in workflow and "自研要在 `选型.md` 写明理由" in workflow


def test_refs_check_extracts_titles_from_standard_bibitem_and_workflows_use_real_template():
    """手写 thebibliography 也要能标题比对，工作流不能指向不存在的 bib。"""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    refs_check = importlib.import_module("refs_check")
    with tempfile.TemporaryDirectory() as tmp:
        tex = os.path.join(tmp, "9.参考文献.tex")
        io.open(tex, "w", encoding="utf-8").write(
            "\\begin{thebibliography}{9}\n"
            "\\bibitem{demo} A. Author.\\newblock A Verifiable Reference Title.\\newblock "
            "Journal of Tests, 2024. doi:10.1234/example.2024.1\n"
            "\\end{thebibliography}\n"
        )
        entries = refs_check.parse_entries(tex)
        assert entries[0][2] == "A Verifiable Reference Title", entries

    for rel in ("workflows/solve-full.md", "workflows/paper-only.md"):
        text = read_repo(rel)
        assert "scripts/refs_check.py 论文/refs.bib" not in text, rel + " 仍把不存在的 refs.bib 当执行路径"
        assert "9.参考文献.tex" in text, rel + " 未说明模板的实际参考文献文件"


def test_no_stale_cross_references_or_dead_paths():
    """跨文件引用会静默过期：表号改了、文件改名了，读者无从察觉。"""
    import re

    workflow = read_repo("workflows/solve-full.md")
    critic = re.search(r"^##\s+Critic\b(.*?)(?=^##\s)",
                       read_repo("references/roles.md"), re.S | re.M).group(1)
    last = max(int(n) for n in re.findall(r"^\|\s*R(\d+)\s*\|", critic, re.M))
    assert "R1–R%d" % last in workflow or "R1-R%d" % last in workflow, \
        "solve-full 引用的 Critic 表号已过期：实际到 R%d" % last

    # 参考文献命令必须指向模板里真实存在的文件
    for rel in ("workflows/solve-full.md", "workflows/paper-only.md"):
        text = read_repo(rel)
        for ref in re.findall(r"refs_check\.py\s+(\S+)", text):
            name = ref.split("/")[-1]
            assert os.path.isfile(os.path.join(ROOT, "assets", "paper", name)), \
                "%s 让 refs_check 读 %s，但 assets/paper/ 里没有这个文件" % (rel, name)


def test_attribution_does_not_claim_imported_assets_as_original():
    """原创清单不能把引自上游的 assets/paper 也算进去——同一文件两种来源自相矛盾。"""
    import re

    text = read_repo("ATTRIBUTION.md")
    block = re.search(r"^##\s+原创部分.*?$(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    assert block, "ATTRIBUTION 缺原创部分小节"
    claims = [line for line in block.group(1).split(chr(10))
              if "assets/paper" in line
              and "不在原创" not in line and "引自" not in line]
    assert not claims, ("assets/paper 引自 Mrite，不能同时被列为原创：" + chr(10)
                        + chr(10).join(claims))


def test_spec_gate_is_split_so_it_does_not_forbid_its_own_output():
    """P-1 不能一边要求写主路线、一边禁止定方法路线——必须拆成两关。"""
    text = read_repo("workflows/solve-full.md")
    assert "P-1a" in text and "P-1b" in text, \
        "P-1 未拆关：写建模详要（含主路线）与「禁止定方法路线」写在同一关里，逻辑打架"


def test_repository_root_carries_no_foreign_scaffolding():
    """根目录只允许白名单内的条目。

    实测事故：一次执行方在本仓根目录拉出了另一套工具的脚手架
    （`.trellis/`、`.agents/`、`.codex/`、`AGENTS.md`），当时没有任何检查能拦住，
    差一步就跟着提交上去。skill 仓只装 skill 本身——别的工具的工作目录不属于这里。
    """
    allowed = {
        ".git", ".gitignore",
        "README.md", "SKILL.md", "ATTRIBUTION.md", "CLAUDE.md", "CODEX.md",
        "routing.yaml", "开题.md",
        "rules", "workflows", "references", "scripts", "assets",
    }
    # 运行期产物与本地缓存不算污染，但也不该被提交（已在 .gitignore 里）
    tolerated = {"__pycache__", "结果", "图", "论文", "求解"}
    found = {name for name in os.listdir(ROOT)}
    foreign = sorted(found - allowed - tolerated)
    assert not foreign, (
        "仓库根目录出现了不属于本 skill 的条目：" + ", ".join(foreign)
        + "。skill 仓只装 skill 本身；别的工具的脚手架请留在它自己的工作目录。")


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
