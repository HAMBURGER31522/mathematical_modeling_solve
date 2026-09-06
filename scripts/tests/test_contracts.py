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
    code, out, err = run("openconf.py")
    assert code == 0, err
    config = as_json(out)
    assert set(config) == {
        "赛事", "正文页数上限", "总页数下限", "图总数下限", "正文引用图下限",
        "摘要页数", "论文模板", "目标图样例目录", "总时限", "主计算机时上限", "本机核数",
    }
    assert config["总页数下限"] == 40


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
                "ques1": {"candidates": [{"name": "基线"}, {"name": "候选模型"}]},
            },
        },
        "questions": {
            "ques1": {
                "candidates": [
                    {"name": "基线", "data_split": split, "ran_ok": True},
                    {"name": "候选模型", "data_split": split, "ran_ok": False},
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
