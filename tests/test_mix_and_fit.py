import json

import numpy as np
import pytest
import soundfile as sf

from conftest import SR, run_script, tone, write_json, write_wav

SCENE = {"lines": [{"id": "01", "who": "hero", "start": 2.0, "end": 3.5, "env": "default", "text": "[shouts] A line"}]}


def build(folder, **mix_flags):
    """A 6 s scene with one line: stems of known content, one take, a fit, and a mix config from make_mix.py."""
    n = 6 * SR
    rng = np.random.default_rng(3)
    music = (rng.standard_normal((n, 2)) * 0.02).astype(np.float32)
    voice = np.zeros((n, 2), dtype=np.float32)
    voice[2 * SR : int(3.5 * SR), :] = tone(220, 1.5, 0.15)[:, None]
    voice[int(4.5 * SR) : 5 * SR, :] = tone(260, 0.5, 0.1)[:, None]  # a grunt outside the line
    write_wav(folder / "voc.wav", voice)
    write_wav(folder / "ins.wav", music)
    (folder / "takes").mkdir()
    write_wav(folder / "takes" / "01_hero.wav", tone(900, 1.4, 0.3))
    write_json(folder / "scene.json", SCENE)
    write_json(folder / "fit.json", {"01": {"orig_on": 2.0, "orig_off": 3.5, "tempo": 1.0, "parts": [{"from": 0.0, "to": 1.4, "start": 2.0, "tempo": 1.0}]}})
    args = ["scene.json", "fit.json", "takes", "mix.json", "--vocals", "voc.wav", "--instrumental", "ins.wav", "--stem-start", "0"]
    for k, v in mix_flags.items():
        args += [f"--{k.replace('_', '-')}"] + ([] if v is True else [v])
    r = run_script("make_mix.py", *args, cwd=folder)
    assert r.returncode == 0, r.stderr
    r = run_script("mix_window.py", "mix.json", cwd=folder)
    assert r.returncode == 0, r.stderr
    mix, _ = sf.read(folder / "out" / "dub_mix.wav", always_2d=True, dtype="float64")
    dub, _ = sf.read(folder / "out" / "dub_only.wav", dtype="float64")
    return mix, dub if dub.ndim == 1 else dub.mean(axis=1), voice.astype(np.float64), music.astype(np.float64)


def gains(mix, dub, voice, music, a, b):
    x, y = int(a * SR), int(b * SR)
    rest = (mix[x:y] - dub[x:y, None]).ravel()
    g = np.linalg.lstsq(np.array([voice[x:y].ravel(), music[x:y].ravel()]).T, rest, rcond=None)[0]
    return 20 * np.log10(np.abs(g) + 1e-12)


def test_default_balance_is_what_the_measurement_finds(tmp_path):
    mix, dub, voice, music = build(tmp_path)
    jp, mu = gains(mix, dub, voice, music, 2.2, 3.3)
    assert abs(jp + 14) < 0.2 and abs(mu + 5) < 0.2
    # Outside the line the original voice only takes the general drop, so breaths and grunts survive.
    jp_out, _ = gains(mix, dub, voice, music, 4.6, 4.9)
    assert abs(jp_out + 5) < 0.2


def test_replace_takes_the_original_line_out(tmp_path):
    mix, dub, voice, music = build(tmp_path, replace=True, music_db=0)
    x, y = int(2.2 * SR), int(3.3 * SR)
    assert np.abs(mix[x:y] - dub[x:y, None] - music[x:y]).max() < 1e-3


def test_duck_lowers_music_only_under_the_dub(tmp_path):
    mix, dub, voice, music = build(tmp_path, music_db=0, voice_db=-14, duck=-17)
    _, under = gains(mix, dub, voice, music, 2.8, 3.2)
    _, clear = gains(mix, dub, voice, music, 0.5, 1.2)
    assert abs(under + 17) < 0.5 and abs(clear) < 0.5


def test_check_levels_reports_the_balance_and_a_sinking_part(tmp_path):
    build(tmp_path)
    r = run_script("check_levels.py", "mix.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "original voice -14.0 dB, music -5.0 dB" in r.stdout
    assert "parts under 6 dB, listen to these: 0" in r.stdout
    # A dub part lowered until it lies under the music must be listed.
    cfg = json.load(open(tmp_path / "mix.json"))
    cfg["lines"]["01"]["parts"][0]["gain_db"] = -45
    write_json(tmp_path / "mix.json", cfg)
    assert run_script("mix_window.py", "mix.json", cwd=tmp_path).returncode == 0
    r = run_script("check_levels.py", "mix.json", cwd=tmp_path)
    assert "listen to these: 1" in r.stdout and "[shouts] A line" in r.stdout


def test_a_window_past_the_stems_stops_with_a_warning_instead_of_crashing(tmp_path):
    build(tmp_path)
    cfg = json.load(open(tmp_path / "mix.json"))
    cfg["end"] = 9.0
    write_json(tmp_path / "mix.json", cfg)
    r = run_script("mix_window.py", "mix.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "the stems end at 6.00 s" in r.stdout
    assert sf.info(tmp_path / "out" / "dub_mix.wav").frames == 6 * SR


def test_make_mix_keeps_the_end_inside_the_stems(tmp_path):
    build(tmp_path)
    r = run_script("make_mix.py", "scene.json", "fit.json", "takes", "m2.json", "--vocals", "voc.wav", "--instrumental", "ins.wav", "--stem-start", 0, "--end", 9, "--out-dir", "trial2", cwd=tmp_path)
    assert "WARNING" in r.stdout
    cfg = json.load(open(tmp_path / "m2.json"))
    assert cfg["end"] == 6.0 and cfg["out_dir"] == "trial2"


def test_a_line_cut_by_the_end_of_the_window_is_reported(tmp_path):
    build(tmp_path)
    cfg = json.load(open(tmp_path / "mix.json"))
    cfg["end"] = 3.0  # the take runs from 2.0 to 3.4
    write_json(tmp_path / "mix.json", cfg)
    r = run_script("mix_window.py", "mix.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "line 01 runs" in r.stdout and "is cut" in r.stdout


def make_take(path, pieces):
    x = np.concatenate([tone(300, s, 0.3) if on else np.zeros(int(s * SR), dtype=np.float32) for on, s in pieces])
    write_wav(path, x)


def fit_one(folder, phrases, next_phrases, pieces):
    (folder / "takes").mkdir(exist_ok=True)
    make_take(folder / "takes" / "01_hero.wav", pieces)
    make_take(folder / "takes" / "02_hero.wav", [(True, 0.5)])
    lines = [{"id": "01", "who": "hero", "text": "One… two"}, {"id": "02", "who": "hero", "text": "Three"}]
    write_json(folder / "scene.json", {"lines": lines})
    write_json(folder / "measure.json", {"01": {"phrases": phrases}, "02": {"phrases": next_phrases}})
    r = run_script("autofit.py", "scene.json", "measure.json", "takes", "fit.json", cwd=folder)
    assert r.returncode == 0, r.stderr
    return json.load(open(folder / "fit.json")), r.stdout


def test_autofit_puts_each_part_on_the_original_phrase(tmp_path):
    fit, out = fit_one(tmp_path, [[10.0, 11.0], [12.0, 13.0]], [[20.0, 21.0]], [(True, 1.0), (False, 0.4), (True, 1.0)])
    parts = fit["01"]["parts"]
    assert [p["start"] for p in parts] == [10.0, 12.0]
    assert all(p["tempo"] == 1.0 for p in parts)
    assert "lines over limit: none" in out


def test_autofit_flags_a_line_that_cannot_fit(tmp_path):
    fit, out = fit_one(tmp_path, [[10.0, 11.0]], [[11.5, 12.0]], [(True, 5.0)])
    assert fit["01"]["tempo"] == 1.30
    assert "OVER" in out and "lines over limit: ['01']" in out


def test_scene_measure_finds_phrases_inside_the_anchors(tmp_path):
    x = np.zeros((6 * SR, 2), dtype=np.float32)
    x[SR : 2 * SR, :] = tone(220, 1.0)[:, None]
    x[int(2.5 * SR) : int(3.5 * SR), :] = tone(220, 1.0)[:, None]
    write_wav(tmp_path / "voc.wav", x)
    write_json(tmp_path / "scene.json", {"lines": [{"id": "01", "who": "hero", "start": 1.0, "end": 3.5, "text": "One… two"}]})
    r = run_script("scene_measure.py", "scene.json", "voc.wav", 0, "measure.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    m = json.load(open(tmp_path / "measure.json"))["01"]
    assert len(m["phrases"]) == 2 and abs(m["talk"] - 2.0) < 0.1
    assert abs(m["f0"] - 220) < 10


@pytest.mark.parametrize("text, tiny", [("[nervous] W-what…", True), ("[nervous] Th-this…", True), ("Wh-WHAT", True), ("[nervous] None…", False), ("Re-entry…", False)])
def test_stammers_of_any_short_length_may_stay_tiny(tmp_path, text, tiny):
    silence = np.zeros(int(0.4 * SR), dtype=np.float32)
    write_wav(tmp_path / "01_hero.wav", np.concatenate([tone(300, 0.2), silence, tone(300, 1.0)]))
    write_json(tmp_path / "scene.json", {"lines": [{"id": "01", "who": "hero", "start": 1.0, "end": 3.5, "text": text}]})
    write_json(tmp_path / "measure.json", {"01": {"phrases": [[1.0, 1.2], [1.8, 3.0]]}})
    r = run_script("autofit.py", "scene.json", "measure.json", tmp_path, "fit.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (len(json.load(open(tmp_path / "fit.json"))["01"]["parts"]) == 2) == tiny


def subtitled_voice(lag):
    """24 lines of speech, with the subtitles moved away from the voice by lag seconds."""
    x = np.zeros(120 * SR, dtype=np.float32)
    lines = []
    for n in range(24):
        start = 1.0 + n * 4.5 + (n % 3) * 0.7
        burst = tone(220, 2.0)
        x[int(start * SR) : int(start * SR) + len(burst)] = burst
        lines.append({"id": f"{n:02d}", "who": "hero", "start": round(start - lag, 2), "end": round(start - lag + 2.0, 2), "text": "x"})
    return x, lines


@pytest.mark.parametrize("lag, warned", [(0.0, False), (2.5, True), (-2.5, True)])
def test_subtitles_from_another_rip_bring_a_warning(tmp_path, lag, warned):
    x, lines = subtitled_voice(lag)
    sf.write(tmp_path / "v.wav", x, SR, subtype="FLOAT")
    write_json(tmp_path / "scene.json", {"lines": lines})
    r = run_script("scene_measure.py", "scene.json", "v.wav", 0, "m.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert ("WARNING: subtitles sit about" in r.stdout) == warned
    if warned:
        assert f"{lag:+.1f} s" in r.stdout


def test_a_short_scene_says_its_timing_was_not_checked(tmp_path):
    x, lines = subtitled_voice(0.0)
    sf.write(tmp_path / "v.wav", x, SR, subtype="FLOAT")
    write_json(tmp_path / "scene.json", {"lines": lines[:5]})
    assert "not checked" in run_script("scene_measure.py", "scene.json", "v.wav", 0, "m.json", cwd=tmp_path).stdout
