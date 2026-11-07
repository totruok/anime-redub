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


def test_letters_work_in_any_script():
    assert dialogue.letters("Don't, Café-5!") == "dontcafe5"
    assert dialogue.letters("¿Qué pasó?") == "quepaso"
    assert dialogue.letters("こんにちは、世界!") == "こんにちは世界"
    assert dialogue.letters("안녕!") == dialogue.letters("안녕")
    assert dialogue.letters("مرحبا!") == "مرحبا"
    assert dialogue.letters("नमस्ते!") != ""


def test_letters_map_latin_back_only_for_russian():
    assert dialogue.letters("Ёлка, ёж!", "ru") == dialogue.letters("елка еж", "ru")
    assert dialogue.letters("nyet", "ru").isalpha() and not dialogue.letters("nyet", "ru").isascii()
    assert dialogue.letters("nyet", "en") == "nyet"


def test_repeated_lines_keep_their_order():
    lines = [{"text": "[shouts] No!"}, {"text": "No-o-o!"}, {"text": "No!"}]
    words = [word("No", 0.0, 0.5), word("No-o-o", 1.0, 2.0), word("No", 3.0, 3.5)]
    spans = dialogue.word_spans(lines, words)
    assert [s[0] for s in spans] == [0.0, 1.0, 3.0]


def test_lead_takes_the_gasp_before_the_first_word():
    lines = [{"text": "[gasps] This", "lead": True}]
    words = [word("(gasp)", 0.2, 0.5, "audio_event"), word("This", 0.6, 1.0)]
    begin, end, first, heard = dialogue.word_spans(lines, words)[0]
    assert (begin, end, first, heard) == (0.2, 1.0, 0.6, "")


def test_a_russian_line_heard_in_latin_letters_keeps_its_boundary():
    lines = [{"text": "\u041d\u0435\u0442"}, {"text": "\u0414\u0430"}]
    words = [word("nyet", 0.0, 0.5), word("da", 1.0, 1.5)]
    assert [s[0] for s in dialogue.word_spans(lines, words, "ru")] == [0.0, 1.0]


def test_a_misheard_first_word_stays_with_its_own_line():
    lines = [{"text": "We left.", "who": "hero"}, {"text": "3 days later we came back.", "who": "rival"}]
    words = [
        {**word("We", 0.0, 0.3), "speaker_id": "a"}, {**word("left", 0.3, 0.6), "speaker_id": "a"},
        {**word("three", 1.2, 1.5), "speaker_id": "b"}, {**word("days", 1.5, 1.8), "speaker_id": "b"}, {**word("later", 1.8, 2.1), "speaker_id": "b"},
        {**word("we", 2.1, 2.3), "speaker_id": "b"}, {**word("came", 2.3, 2.5), "speaker_id": "b"}, {**word("back", 2.5, 2.8), "speaker_id": "b"},
    ]
    spans = dialogue.word_spans(lines, words, "en")
    assert spans[1][0] == 1.2
    assert "three" in spans[1][3]


def test_a_lost_line_brings_a_warning_and_the_later_lines_recover(capsys):
    lost = "and then a very long passage of speech that the performance never actually said aloud at all " * 3
    written = ["first line here", lost, "the third line", "the fourth line", "the fifth line", "the sixth line", "the seventh line", "the last line"]
    tokens, starts = [], {}
    for n, line in enumerate(written):
        if line is not lost:
            starts[n] = len(tokens)
            tokens += line.split()
    spans = dialogue.word_spans([{"text": t} for t in written], timed(tokens), "en")
    assert [spans[n][2] for n in (6, 7)] == [float(starts[n]) for n in (6, 7)]
    assert "barely matches" in capsys.readouterr().out


def test_a_lost_line_is_not_hidden_by_the_narrow_search():
    # The narrow search alone still finds a path here, and it puts every later line on the wrong words.
    start = ["first line here", "a passage of speech that the performance never actually said aloud at all and nobody heard it " * 2]
    rest = ["the third line goes on a little", "the fourth line goes on as well", "now the fifth line is here", "and the sixth line follows it",
            "the seventh line comes after", "and then the eighth line too", "this ninth line is nearly last",
            "and finally the very last line runs on for quite a long time because the speaker refuses to stop talking about everything that happened on that long and terrible day"]
    tokens = (start[0] + " " + " ".join(rest)).split()
    spans = dialogue.word_spans([{"text": t} for t in start + rest], timed(tokens), "en")
    expected, at = [], len(start[0].split())
    for line in rest:
        expected.append(float(at))
        at += len(line.split())
    assert [s[2] for s in spans[3:]] == expected[1:]


def test_lines_in_another_alphabet_bring_a_warning(capsys):
    lines = [{"text": "\u0414\u043e\u0431\u0430\u0440 \u0434\u0430\u043d", "id": "01"}]
    dialogue.word_spans(lines, [word("Dobar", 0.0, 0.5), word("dan", 0.5, 1.0)], "sr")
    assert "WARNING: line 01" in capsys.readouterr().out


def timed(tokens, start=0.0):
    return [word(t, start + n, start + n + 0.9) for n, t in enumerate(tokens)]


def test_a_line_of_many_short_words_is_matched():
    long_line = "I told you that we would all be back before the sun goes down and nobody would ever notice we were gone"
    short_line = "You lied"
    tokens = long_line.split() + short_line.split()
    spans = dialogue.word_spans([{"text": long_line}, {"text": short_line}], timed(tokens), "en")
    assert len(long_line.split()) > 16
    assert spans[1][0] == float(len(long_line.split()))


def test_a_full_block_of_one_character_tokens_takes_reasonable_time():
    import time

    line = "我告诉过你我们都会在太阳下山之前回来"
    lines = [{"text": line}] * 50
    t = time.time()
    spans = dialogue.word_spans(lines, timed(list(line * 50)), "zh")
    assert time.time() - t < 60
    assert spans[-1][0] == float(len(line) * 49)


def test_a_language_of_one_character_tokens_is_matched():
    first = "我告诉过你我们都会在太阳下山之前回来而且没有人会注意到我们曾经离开过这里"
    second = "你骗了我"
    spans = dialogue.word_spans([{"text": first}, {"text": second}], timed(list(first + second)), "zh")
    assert len(first) > 16
    assert spans[1][0] == float(len(first))


@pytest.fixture
def block(tmp_path):
    lines = [
        {"id": "01", "who": "hero", "start": 0, "end": 1, "text": "[shouts] First line"},
        {"id": "02", "who": "rival", "start": 2, "end": 3, "text": "Second line"},
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
    seen = []

    def run(cmd, *a, **k):
        if any("scribe.py" in str(c) for c in cmd):
            seen.append(cmd)
            words = [word("First", 0.0, 0.5), word("line", 0.5, 1.0), word("Second", 1.5, 2.0), word("line", 2.0, 2.5)]
            with open(cmd[3], "w") as f:
                json.dump({"words": words}, f)
            return subprocess.CompletedProcess(cmd, 0)
        return real(cmd, *a, **k)

    monkeypatch.setattr(dialogue.subprocess, "run", run)
    return seen


@pytest.fixture
def fake_api(block, monkeypatch):
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
    return calls


def test_generation_cuts_takes_and_never_pays_twice(block, fake_api, monkeypatch):
    calls = fake_api
    fake_scribe(monkeypatch)
    run_main(monkeypatch, block, "--language", "en", "--collect", str(block / "takes"))
    assert len(calls) == 1
    assert calls[0]["model_id"] == "eleven_v4" and calls[0]["settings"]["stability"] == 0.0
    assert [i["voice_id"] for i in calls[0]["inputs"]] == ["v1", "v2"]

    first, _ = sf.read(block / "takes" / "01_hero.wav")
    second, _ = sf.read(block / "takes" / "02_rival.wav")
    assert 0.9 < len(first) / SR < 1.6 and 0.9 < len(second) / SR < 1.6
    assert json.load(open(block / "takes" / "02_rival.json"))["first_word"] >= 0

    run_main(monkeypatch, block, "--language", "en")  # same text and settings: cached
    assert len(calls) == 1


def test_the_language_reaches_generation_and_recognition_and_is_part_of_the_cache_key(block, fake_api, monkeypatch):
    calls = fake_api
    seen = fake_scribe(monkeypatch)
    run_main(monkeypatch, block, "--language", "de")
    assert calls[0]["language_code"] == "de"
    assert seen[0][seen[0].index("--language") + 1] == "de"

    passed = []
    real = dialogue.word_spans
    monkeypatch.setattr(dialogue, "word_spans", lambda lines, words, language=None: passed.append(language) or real(lines, words, language))
    run_main(monkeypatch, block, "--language", "de")  # a free rerun still matches in the chosen language
    assert passed == ["de"]

    run_main(monkeypatch, block, "--language", "fr")  # the same text in another language is a new request
    assert [c["language_code"] for c in calls] == ["de", "fr"]


def test_the_language_is_required_and_checked_before_any_call(block, monkeypatch):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, block)
    with pytest.raises(SystemExit, match="xx"):
        run_main(monkeypatch, block, "--language", "xx")


def test_a_request_over_the_limit_is_refused_before_any_call(block, monkeypatch):
    lines = json.load(open(block / "block.json"))["lines"]
    lines[0]["text"] = "a" * 2100
    write_json(block / "block.json", {"lines": lines})
    with pytest.raises(SystemExit, match="make_blocks"):
        run_main(monkeypatch, block, "--language", "en")  # the conftest guard would fail the test on any real call


def test_a_character_missing_from_the_cast_is_refused_before_any_call(block, monkeypatch):
    write_json(block / "cast.json", {"hero": {"voice_id": "v1"}})
    with pytest.raises(SystemExit, match="rival"):
        run_main(monkeypatch, block, "--language", "en")
