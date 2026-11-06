import json
import os

import cost
import make_blocks
from conftest import run_script, write_json


def line(i, chars, start, end):
    return {"id": f"{i:02d}", "who": "hero", "start": start, "end": end, "ru": "а" * chars}


def test_blocks_keep_order_stay_under_limit_and_cut_at_the_longest_pause():
    lines = [line(1, 300, 0, 1), line(2, 300, 1.1, 2), line(3, 300, 12, 13), line(4, 300, 13.1, 14), line(5, 300, 14.2, 15)]
    blocks = make_blocks.split(lines, 1000)
    assert [l["id"] for b in blocks for l in b] == ["01", "02", "03", "04", "05"]
    assert all(sum(len(l["ru"]) for l in b) <= 1000 for b in blocks)
    assert blocks[0][-1]["id"] == "02"  # the 10 s pause, not the last line that fits


def test_blocks_refuse_a_line_over_the_limit():
    try:
        make_blocks.split([line(1, 3000, 0, 1)], 1000)
    except SystemExit as e:
        assert "01" in str(e)
    else:
        raise AssertionError("expected a refusal")


def test_cost_of_the_measured_scene():
    lines = [{"ru": "[tag] " + "а" * 94}] * 20  # 2000 characters
    e = cost.estimate(lines)
    assert abs(e["generation"] - 0.16) < 1e-9
    assert e["spoken"] == 94 * 20
    assert cost.estimate(lines, passes=2)["generation"] == 2 * e["generation"]


def test_subtitles_ass_and_srt_become_a_draft(tmp_path):
    ass = tmp_path / "a.ass"
    ass.write_text(
        "[Events]\n"
        "Dialogue: 0,0:00:10.00,0:00:12.00,Main,,0,0,0,,{\\i1}Hello\\Nthere\n"
        "Dialogue: 0,0:00:30.00,0:00:31.00,Main,,0,0,0,,Too late\n",
        encoding="utf-8",
    )
    draft = tmp_path / "scene.json"
    r = run_script("subs_window.py", ass, 5, 20, "--draft", draft)
    assert r.returncode == 0, r.stderr
    lines = json.load(open(draft))["lines"]
    assert [(l["id"], l["start"], l["end"], l["original"], l["who"]) for l in lines] == [("01", 10.0, 12.0, "Hello there", "?")]

    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:10,500 --> 00:00:12,000\n<i>Hi</i>\nyou\n\n2\n00:01:00,000 --> 00:01:01,000\nLater\n", encoding="utf-8")
    r = run_script("subs_window.py", srt, 0, 20)
    assert "Hi you" in r.stdout and "Later" not in r.stdout


def test_scribe_lines_become_a_draft_at_source_times(tmp_path):
    tsv = tmp_path / "jp.lines.tsv"
    tsv.write_text("1.00\t2.00\tspeaker_0\tこんにちは\n50.00\t51.00\tspeaker_1\tさようなら\n", encoding="utf-8")
    draft = tmp_path / "scene.json"
    r = run_script("subs_window.py", tsv, 100, 120, "--offset", 100, "--draft", draft)
    assert r.returncode == 0, r.stderr
    assert [(l["start"], l["original"]) for l in json.load(open(draft))["lines"]] == [(101.0, "こんにちは")]


def test_an_unfinished_draft_is_refused_before_it_can_cost_anything(tmp_path):
    write_json(tmp_path / "scene.json", {"lines": [{"id": "01", "who": "?", "start": 0, "end": 1, "ru": ""}]})
    for script, args in (("cost.py", ["scene.json"]), ("make_blocks.py", ["scene.json", "blocks"])):
        r = run_script(script, *args, cwd=tmp_path)
        assert r.returncode != 0 and "01" in r.stderr, script
    assert not (tmp_path / "blocks").exists()


def test_doctor_runs_and_never_prints_the_key(tmp_path):
    r = run_script("doctor.py", cwd=tmp_path)
    assert "ELEVENLABS_API_KEY is set" in r.stdout
    assert "test-key" not in r.stdout + r.stderr
    assert os.path.exists(os.path.join(os.path.dirname(cost.__file__), "doctor.py"))


def test_mix_config_needs_stems(tmp_path):
    write_json(tmp_path / "fit.json", {})
    r = run_script("make_mix.py", "scene.json", tmp_path / "fit.json", "takes", tmp_path / "mix.json")
    assert r.returncode != 0 and "--stems" in r.stderr
