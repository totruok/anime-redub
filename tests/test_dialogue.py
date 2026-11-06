import base64
import json
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

import dialogue
from conftest import SR, tone, write_json


def word(text, start, end, kind="word"):
    return {"text": text, "start": start, "end": end, "type": kind}


def test_letters_keep_only_cyrillic_and_transliterate_latin():
    assert dialogue.letters("Ёлка, ёж!") == "елкаеж"
    assert dialogue.letters("nyet") != ""


def test_repeated_lines_keep_their_order():
    lines = [{"ru": "[shouts] Нет!"}, {"ru": "Не-е-ет!"}, {"ru": "Нет!"}]
    words = [word("Нет", 0.0, 0.5), word("Не-е-ет", 1.0, 2.0), word("Нет", 3.0, 3.5)]
    spans = dialogue.word_spans(lines, words)
    assert [s[0] for s in spans] == [0.0, 1.0, 3.0]


def test_lead_takes_the_gasp_before_the_first_word():
    lines = [{"ru": "[gasps] Это", "lead": True}]
    words = [word("(gasp)", 0.2, 0.5, "audio_event"), word("Это", 0.6, 1.0)]
    begin, end, first = dialogue.word_spans(lines, words)[0]
    assert (begin, end, first) == (0.2, 1.0, 0.6)


@pytest.fixture
def block(tmp_path):
    lines = [
        {"id": "01", "who": "hero", "start": 0, "end": 1, "ru": "[shouts] Первая реплика"},
        {"id": "02", "who": "rival", "start": 2, "end": 3, "ru": "Вторая реплика"},
    ]
    write_json(tmp_path / "block.json", {"lines": lines})
    write_json(tmp_path / "cast.json", {"hero": {"voice_id": "v1"}, "rival": {"voice_id": "v2"}})
    # A fake generated request: two bursts with a pause between them.
    x = np.concatenate([tone(300, 1.0), np.zeros(SR // 2, dtype=np.float32), tone(500, 1.0)])
    sf.write(tmp_path / "gen.wav", x, SR, subtype="PCM_16")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", tmp_path / "gen.wav", tmp_path / "gen.mp3"], check=True)
    return tmp_path


def run_main(monkeypatch, folder, *extra):
    monkeypatch.setattr(sys, "argv", ["dialogue.py", str(folder / "block.json"), str(folder / "cast.json"), str(folder / "out"), *extra])
    dialogue.main()


def fake_scribe(monkeypatch):
    real = subprocess.run

    def run(cmd, *a, **k):
        if any("scribe.py" in str(c) for c in cmd):
            words = [word("Первая", 0.0, 0.5), word("реплика", 0.5, 1.0), word("Вторая", 1.5, 2.0), word("реплика", 2.0, 2.5)]
            with open(cmd[3], "w") as f:
                json.dump({"words": words}, f)
            return subprocess.CompletedProcess(cmd, 0)
        return real(cmd, *a, **k)

    monkeypatch.setattr(dialogue.subprocess, "run", run)


def test_generation_cuts_takes_and_never_pays_twice(block, monkeypatch):
    calls = []

    class Response:
        ok = True
        headers = {"character-cost": "37"}
        status_code = 200

        def json(self):
            audio = base64.b64encode(open(block / "gen.mp3", "rb").read()).decode()
            return {"audio_base64": audio, "voice_segments": [{"voice_id": "v1", "dialogue_input_index": 0}, {"voice_id": "v2", "dialogue_input_index": 1}]}

    def post(url, **k):
        calls.append(k["json"])
        return Response()

    monkeypatch.setattr(dialogue.requests, "post", post)
    fake_scribe(monkeypatch)
    run_main(monkeypatch, block, "--collect", str(block / "takes"))
    assert len(calls) == 1
    assert calls[0]["model_id"] == "eleven_v4" and calls[0]["settings"]["stability"] == 0.0
    assert [i["voice_id"] for i in calls[0]["inputs"]] == ["v1", "v2"]

    first, _ = sf.read(block / "takes" / "01_hero.wav")
    second, _ = sf.read(block / "takes" / "02_rival.wav")
    assert 0.9 < len(first) / SR < 1.6 and 0.9 < len(second) / SR < 1.6
    assert json.load(open(block / "takes" / "02_rival.json"))["first_word"] >= 0

    run_main(monkeypatch, block)  # same text and settings: cached
    assert len(calls) == 1


def test_a_request_over_the_limit_is_refused_before_any_call(block, monkeypatch):
    lines = json.load(open(block / "block.json"))["lines"]
    lines[0]["ru"] = "а" * 2100
    write_json(block / "block.json", {"lines": lines})
    with pytest.raises(SystemExit, match="make_blocks"):
        run_main(monkeypatch, block)  # the conftest guard would fail the test on any real call


def test_a_character_missing_from_the_cast_is_refused_before_any_call(block, monkeypatch):
    write_json(block / "cast.json", {"hero": {"voice_id": "v1"}})
    with pytest.raises(SystemExit, match="rival"):
        run_main(monkeypatch, block)
