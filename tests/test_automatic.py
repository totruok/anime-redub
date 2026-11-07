"""The whole pipeline runs without a listener, and the spending limit holds. No real API is involved."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

import budget
import design_voices
import fake_elevenlabs
import save_voices
from conftest import SCRIPTS, run_script, tone, write_json

COMMON = "Dry, close microphone."
SCENE = [
    {"who": "hero", "start": 1.0, "end": 2.5, "text": "[shouts] Halt! Du kommst hier nicht vorbei!"},
    {"who": "rival", "start": 3.5, "end": 5.0, "text": "[amused] Willst du mich wirklich aufhalten?"},
    {"who": "hero", "start": 6.0, "end": 7.5, "text": "[nervous] W-was war das bloß?"},
]


@pytest.fixture
def api(monkeypatch):
    fake_elevenlabs.Handler.log.clear()
    server = fake_elevenlabs.start()
    monkeypatch.setenv("ELEVENLABS_API_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield fake_elevenlabs.Handler.log
    server.shutdown()


@pytest.fixture
def folder(tmp_path):
    """A source video and its stems, with speech-like bursts where the subtitles say."""
    sr = 44100
    voice = np.zeros(int(9 * sr), dtype=np.float32)
    for line in SCENE:
        a = int(line["start"] * sr)
        burst = tone(220, line["end"] - line["start"])
        voice[a : a + len(burst)] = burst
    music = tone(90, 9, level=0.02)
    (tmp_path / "stems").mkdir()
    sf.write(tmp_path / "stems" / "vocals.wav", np.stack([voice, voice], axis=1), sr, subtype="FLOAT")
    sf.write(tmp_path / "stems" / "instrumental.wav", np.stack([music, music], axis=1), sr, subtype="FLOAT")
    write_json(tmp_path / "stems" / "stems.json", {"vocals": "vocals.wav", "instrumental": "instrumental.wav", "start": 0.0})
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=9", "-f", "lavfi", "-i", "sine=f=220:d=9", "-shortest", tmp_path / "source.mp4"], check=True)
    srt = "".join(f"{n}\n00:00:0{int(l['start'])},000 --> 00:00:0{int(l['end'])},500\nOriginal line {n}\n\n" for n, l in enumerate(SCENE, 1))
    (tmp_path / "subs.srt").write_text(srt, encoding="utf-8")
    write_json(tmp_path / "characters.json", {
        "project": "Test",
        "common": COMMON,
        "characters": [
            {"key": "hero", "name": "Hero", "role": "hero", "description": "Young man, light tenor.", "text": "[shouts] Halt! " * 10},
            {"key": "rival", "name": "Rival", "role": "villain", "description": "Older man, deep baritone.", "text": "[amused] Wirklich? " * 8},
        ],
    })
    return tmp_path


def step(folder, script, *args):
    r = run_script(script, *args, cwd=folder)
    assert r.returncode == 0, f"{script}: {r.stdout}\n{r.stderr}"
    return r.stdout


def test_one_launch_gets_from_source_to_video_with_no_listener(api, folder):
    step(folder, "budget.py", "set", "2")
    step(folder, "subs_window.py", "subs.srt", 0, 9, "--draft", "scene.json")

    # What Claude does between the scripts: who speaks and what they say.
    scene = json.load(open(folder / "scene.json"))
    assert len(scene["lines"]) == len(SCENE)
    for line, written in zip(scene["lines"], SCENE):
        line.update(who=written["who"], text=written["text"], env="room")
    write_json(folder / "scene.json", scene)

    step(folder, "scene_measure.py", "scene.json", "stems/vocals.wav", 0, "measure.json")
    step(folder, "design_voices.py", "characters.json", "previews", "--language", "de")
    chosen = step(folder, "save_voices.py", "characters.json", "previews", "cast.json", "--auto")
    assert "chosen automatically" in chosen
    assert set(json.load(open(folder / "cast.json"))) == {"hero", "rival"}

    step(folder, "make_blocks.py", "scene.json", "blocks")
    step(folder, "dialogue.py", "blocks/block_01.json", "cast.json", "gen", "--language", "de", "--collect", "takes")
    step(folder, "autofit.py", "scene.json", "measure.json", "takes", "fit.json")
    step(folder, "make_mix.py", "scene.json", "fit.json", "takes", "mix.json", "--stems", "stems")
    step(folder, "mix_window.py", "mix.json")
    assert "balance inside lines" in step(folder, "check_levels.py", "mix.json")
    subprocess.run([os.path.join(SCRIPTS, "render.sh"), "source.mp4", "0", "9", "out/dub_mix.wav", "dub.mp4", "0"], cwd=folder, check=True, capture_output=True)

    assert (folder / "dub.mp4").stat().st_size > 1000 and (folder / "dub_timing.mp4").stat().st_size > 1000
    spent = json.load(open(folder / "budget.json"))
    assert 0 < spent["spent"] <= spent["limit"]
    assert api.count("/v1/text-to-dialogue/with-timestamps") == 1 and api.count("/v1/speech-to-text") == 1


def test_a_scene_of_several_blocks_goes_as_the_skill_says(api, folder):
    write_json(folder / "scene.json", {"lines": [{"id": f"{n:02d}", "env": "room", **line} for n, line in enumerate(SCENE, 1)]})
    step(folder, "scene_measure.py", "scene.json", "stems/vocals.wav", 0, "measure.json")
    write_json(folder / "cast.json", {"hero": {"voice_id": "v1"}, "rival": {"voice_id": "v2"}})
    step(folder, "make_blocks.py", "scene.json", "blocks", "--max-chars", "60")
    blocks = sorted(os.listdir(folder / "blocks"))
    assert len(blocks) >= 2

    # After block 1 alone, the table is complete for that block, and the command stops at the next one with no fit.json.
    step(folder, "dialogue.py", f"blocks/{blocks[0]}", "cast.json", "gen", "--language", "de", "--collect", "takes")
    first_of_next = json.load(open(folder / "blocks" / blocks[1]))["lines"][0]["id"]
    r = run_script("autofit.py", "scene.json", "measure.json", "takes", "fit.json", cwd=folder)
    assert r.returncode != 0 and f"no take for line {first_of_next}" in r.stderr
    assert "01 hero" in r.stdout and not (folder / "fit.json").exists()

    for block in blocks[1:]:
        step(folder, "dialogue.py", f"blocks/{block}", "cast.json", "gen", "--language", "de", "--collect", "takes")
    step(folder, "autofit.py", "scene.json", "measure.json", "takes", "fit.json")
    assert set(json.load(open(folder / "fit.json"))) == {"01", "02", "03"}


def test_the_budget_stops_a_paid_step_before_anything_is_sent(api, folder):
    step(folder, "budget.py", "set", "0.001")
    r = run_script("design_voices.py", "characters.json", "previews", "--language", "de", cwd=folder)
    assert r.returncode != 0 and "BUDGET" in r.stderr
    assert api == []


def test_the_budget_stops_generation_and_recognition_too(api, tmp_path):
    write_json(tmp_path / "block.json", {"lines": [{"id": "01", "who": "hero", "start": 0, "end": 1, "text": "Hallo " * 20}]})
    write_json(tmp_path / "cast.json", {"hero": {"voice_id": "v1"}})
    step(tmp_path, "budget.py", "set", "0.001")
    r = run_script("dialogue.py", "block.json", "cast.json", "gen", "--language", "de", cwd=tmp_path)
    assert r.returncode != 0 and "BUDGET" in r.stderr and api == []

    sf.write(tmp_path / "long.wav", np.zeros(44100 * 60, dtype=np.float32), 44100, subtype="PCM_16")
    r = run_script("scribe.py", "long.wav", "out.json", cwd=tmp_path)
    assert r.returncode != 0 and "BUDGET" in r.stderr and api == []


def test_no_budget_file_means_no_limit_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    budget.charge(1000, "anything")
    budget.refund(1000)
    assert "NO LIMIT" in capsys.readouterr().out
    assert not os.path.exists("budget.json")
    assert budget.scribe_cost("no-such-file") == 0.0


def test_every_paid_step_is_counted_once_and_earlier_spending_stops_the_next(api, folder):
    spent = lambda: json.load(open(folder / "budget.json"))["spent"]  # noqa: E731
    step(folder, "budget.py", "set", "5")
    step(folder, "design_voices.py", "characters.json", "previews", "--language", "de")
    voices = spent()
    assert voices == pytest.approx(budget.text_cost(sum(len(c["text"]) for c in json.load(open(folder / "characters.json"))["characters"])), abs=1e-3)

    write_json(folder / "cast.json", {"hero": {"voice_id": "v1"}})
    write_json(folder / "block.json", {"lines": [{"id": "01", "who": "hero", "start": 0, "end": 1, "text": "Hallo Welt und alle anderen"}]})
    step(folder, "dialogue.py", "block.json", "cast.json", "gen", "--language", "de")
    generated = spent()
    assert generated > voices

    calls = len(api)
    step(folder, "design_voices.py", "characters.json", "previews", "--language", "de")
    step(folder, "dialogue.py", "block.json", "cast.json", "gen", "--language", "de")
    assert spent() == generated and len(api) == calls  # a rerun comes from the cache and is free

    step(folder, "budget.py", "set", str(generated + 0.0001))
    assert spent() == generated  # a new limit keeps what has been spent
    write_json(folder / "block.json", {"lines": [{"id": "01", "who": "hero", "start": 0, "end": 1, "text": "Eine andere Zeile gleicher Art"}]})
    r = run_script("dialogue.py", "block.json", "cast.json", "gen", "--language", "de", cwd=folder)
    assert r.returncode != 0 and "BUDGET" in r.stderr and len(api) == calls


class Refused:
    ok = False
    status_code = 500
    url = "http://fake"
    text = "server error"
    headers = {}


def test_a_lost_response_stays_counted_and_a_refusal_is_given_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_json("characters.json", {"common": "c", "characters": [{"key": "hero", "name": "H", "role": "r", "description": "d", "text": "x" * 500}]})
    budget.write({"spent": 0.0, "limit": 1.0})
    monkeypatch.setattr(sys, "argv", ["design_voices.py", "characters.json", "previews", "--language", "de"])

    monkeypatch.setattr(design_voices.requests, "post", lambda url, **k: Refused())
    with pytest.raises(SystemExit):
        design_voices.main()
    assert budget.read()["spent"] == 0.0

    def lost(url, **k):
        raise design_voices.requests.ConnectionError("dropped")

    monkeypatch.setattr(design_voices.requests, "post", lost)
    with pytest.raises(design_voices.requests.ConnectionError):
        design_voices.main()
    assert budget.read()["spent"] == pytest.approx(0.04)


def test_blocks_started_together_cannot_pass_the_limit(tmp_path):
    write_json(tmp_path / "budget.json", {"spent": 0.0, "limit": 0.05})
    code = "import budget; budget.charge(0.01, 'x')"
    env = dict(os.environ, PYTHONPATH=SCRIPTS)
    runs = [subprocess.Popen([sys.executable, "-c", code], cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(12)]
    passed = sum(p.wait() == 0 for p in runs)
    assert passed == 5
    assert json.load(open(tmp_path / "budget.json"))["spent"] == pytest.approx(0.05)


def preview_folder(tmp_path):
    sr = 22050
    write_json(tmp_path / "characters.json", {"common": "c", "characters": [
        {"key": "hero", "name": "Hero", "description": "d"}, {"key": "rival", "name": "Rival", "description": "d"},
    ]})
    pitches = {"hero": {"A": 200, "B": 900, "C": 900}, "rival": {"A": 210, "B": 215, "C": 1500}}
    languages = {"hero": ("de", "de", "de"), "rival": ("de", "de", "de")}
    for key, voices in pitches.items():
        previews = []
        for (letter, pitch), code in zip(voices.items(), languages[key]):
            name = f"{key}_{letter}.wav"
            sf.write(tmp_path / name, tone(pitch, 1.0, sr=sr), sr, subtype="PCM_16")
            previews.append({"letter": letter, "file": name, "generated_voice_id": f"{key}{letter}", "language": code})
        write_json(tmp_path / f"{key}.json", {"key": key, "language": "de", "previews": previews})
    return json.load(open(tmp_path / "characters.json"))


def test_automatic_choice_keeps_the_voices_apart(tmp_path):
    cfg = preview_folder(tmp_path)
    assert save_voices.auto_picks(cfg, str(tmp_path)) == ["hero=A", "rival=C"]


def test_automatic_choice_skips_previews_in_another_language(tmp_path):
    cfg = preview_folder(tmp_path)
    meta = json.load(open(tmp_path / "rival.json"))
    meta["previews"][2]["language"] = "en"  # the most distinct one, in the wrong language
    write_json(tmp_path / "rival.json", meta)
    assert save_voices.auto_picks(cfg, str(tmp_path))[1] != "rival=C"


def test_automatic_choice_keeps_voices_already_cast(tmp_path):
    cfg = preview_folder(tmp_path)
    assert save_voices.auto_picks(cfg, str(tmp_path), {"rival": {"voice_id": "x", "generated_voice_id": "rivalB"}})[0] == "rival=B"
    assert save_voices.auto_picks(cfg, str(tmp_path), {"hero": {"voice_id": "by hand"}}) == ["rival=A"]
    # A voice from another folder is not among these previews, so that character gets a new one.
    assert "hero=A" in save_voices.auto_picks(cfg, str(tmp_path), {"hero": {"voice_id": "x", "generated_voice_id": "elsewhere"}})


def test_the_same_letter_from_a_new_folder_is_a_new_voice(tmp_path, monkeypatch):
    preview_folder(tmp_path)
    write_json(tmp_path / "cast.json", {"hero": {"voice_id": "old", "letter": "A", "generated_voice_id": "from another language"}})
    sent = []

    class Response:
        ok = True

        def json(self):
            return {"voice_id": "new"}

    def post(url, **k):
        sent.append(k["json"]["generated_voice_id"])
        return Response()

    monkeypatch.setattr(save_voices.requests, "post", post)
    monkeypatch.setattr(sys, "argv", ["save_voices.py", str(tmp_path / "characters.json"), str(tmp_path), str(tmp_path / "cast.json"), "hero=A"])
    save_voices.main()
    assert sent == ["heroA"] and json.load(open(tmp_path / "cast.json"))["hero"]["voice_id"] == "new"

    save_voices.main()  # the very same preview again: nothing to do
    assert len(sent) == 1


def test_either_auto_or_picks(tmp_path):
    preview_folder(tmp_path)
    for args in ([], ["--auto", "hero=A"]):
        r = run_script("save_voices.py", tmp_path / "characters.json", tmp_path, tmp_path / "cast.json", *args)
        assert r.returncode != 0 and "--auto" in r.stderr
