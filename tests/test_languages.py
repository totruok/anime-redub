import json
import sys

import pytest

import design_voices
import languages
import scribe
from conftest import run_script, write_json

AUDIO = b"not really audio"


def test_every_code_has_a_name_and_an_unknown_one_stops_the_run():
    assert languages.check("de") == "German"
    for bad in ("xx", "russian", "RU", ""):
        with pytest.raises(SystemExit):
            languages.check(bad)


def test_the_list_prints():
    r = run_script("languages.py")
    assert r.returncode == 0 and "es   Spanish" in r.stdout and "yue  Cantonese" in r.stdout


class VoiceResponse:
    ok = True
    status_code = 200
    headers = {"character-cost": "120"}

    def __init__(self, language):
        self.language = language

    def json(self):
        previews = [{"audio_base_64": "QUJD", "generated_voice_id": f"g{n}", "duration_secs": 3.0, "language": self.language} for n in range(3)]
        return {"text": "preview", "previews": previews}


@pytest.fixture
def characters(tmp_path):
    write_json(tmp_path / "characters.json", {
        "common": "Dry, close microphone.",
        "characters": [{"key": "hero", "name": "Hero", "role": "hero", "description": "Young man.", "text": "x" * 120}],
    })
    return tmp_path


def run_design(monkeypatch, folder, *extra):
    monkeypatch.setattr(sys, "argv", ["design_voices.py", str(folder / "characters.json"), str(folder / "previews"), *extra])
    design_voices.main()


def test_voices_are_described_in_the_chosen_language_and_never_paid_for_twice(characters, monkeypatch, capsys):
    calls = []

    def post(url, **k):
        calls.append(k["json"])
        return VoiceResponse("de")

    monkeypatch.setattr(design_voices.requests, "post", post)
    run_design(monkeypatch, characters, "--language", "de")
    assert calls[0]["voice_description"] == "Young man. Native German speaker. Dry, close microphone."
    assert json.load(open(characters / "previews" / "hero.json"))["language"] == "de"
    assert "WARNING" not in capsys.readouterr().out

    run_design(monkeypatch, characters, "--language", "de")
    assert len(calls) == 1


def test_previews_in_another_language_bring_a_warning(characters, monkeypatch, capsys):
    monkeypatch.setattr(design_voices.requests, "post", lambda url, **k: VoiceResponse("en"))
    run_design(monkeypatch, characters, "--language", "de")
    assert "WARNING" in capsys.readouterr().out


def test_previews_of_another_language_are_not_reused(characters, monkeypatch):
    monkeypatch.setattr(design_voices.requests, "post", lambda url, **k: VoiceResponse("de"))
    run_design(monkeypatch, characters, "--language", "de")
    with pytest.raises(SystemExit, match="another folder"):
        run_design(monkeypatch, characters, "--language", "fr")


def test_voice_design_needs_a_known_language_before_any_call(characters, monkeypatch):
    with pytest.raises(SystemExit):
        run_design(monkeypatch, characters)
    with pytest.raises(SystemExit, match="xx"):
        run_design(monkeypatch, characters, "--language", "xx")


class ScribeResponse:
    ok = True
    status_code = 200
    headers = {}

    def json(self):
        return {"language_code": "jpn", "language_probability": 1.0, "words": []}


def test_changed_voice_text_keeps_the_previews_and_says_so(characters, monkeypatch, capsys):
    monkeypatch.setattr(design_voices.requests, "post", lambda url, **k: VoiceResponse("de"))
    run_design(monkeypatch, characters, "--language", "de")
    capsys.readouterr()
    cfg = json.load(open(characters / "characters.json"))
    cfg["characters"][0]["text"] = "y" * 120
    write_json(characters / "characters.json", cfg)
    run_design(monkeypatch, characters, "--language", "de")
    assert "kept" in capsys.readouterr().out


def test_scribe_keeps_the_spaces_between_words(tmp_path):
    words = [{"text": "Bonjour", "start": 0.0, "end": 0.5, "type": "word", "speaker_id": "a"},
             {"text": " ", "start": 0.5, "end": 0.5, "type": "spacing", "speaker_id": "a"},
             {"text": "toi", "start": 0.5, "end": 0.8, "type": "word", "speaker_id": "a"}]
    write_json(tmp_path / "t.json", {"words": words})
    r = run_script("scribe.py", "no-audio-needed", "t.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "t.lines.tsv").read_text(encoding="utf-8").strip().split("\t")[3] == "Bonjour toi"


@pytest.mark.parametrize("extra, expected", [([], None), (["--language", "ja"], "ja")])
def test_scribe_detects_the_language_unless_told(tmp_path, monkeypatch, extra, expected):
    (tmp_path / "a.mp3").write_bytes(AUDIO)
    forms = []

    def post(url, **k):
        forms.append(k["data"])
        return ScribeResponse()

    monkeypatch.setattr(scribe.requests, "post", post)
    monkeypatch.setattr(sys, "argv", ["scribe.py", str(tmp_path / "a.mp3"), str(tmp_path / "out.json"), *extra])
    scribe.main()
    assert forms[0].get("language_code") == expected
