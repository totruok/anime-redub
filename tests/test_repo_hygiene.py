"""This repository is shared in public: no media, no secrets, no personal paths, nobody's dub named."""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = (".wav", ".mp3", ".flac", ".m4a", ".aac", ".ac3", ".mka", ".mkv", ".mp4", ".avi", ".webm", ".ass", ".ssa", ".srt", ".ckpt", ".torrent", ".zip")
SECRETS = [r"sk_[0-9a-f]{20,}", r"xi-api-key\s*[:=]\s*['\"][^'\"]{10,}"]
# Built in pieces so that this file does not match itself.
PERSONAL = ["/Us" + "ers/", "zoe" + "_voice", "secre" + "tary/", "ts.totr" + "uok"]
UNNAMED = ["Dru" + "aga", "Cub" + "a77", "Za" + "RT"]


def files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def test_files_are_listed():
    assert any(f.endswith("SKILL.md") for f in files())


def test_no_media_and_nothing_large():
    for f in files():
        assert not f.lower().endswith(MEDIA), f
        assert os.path.getsize(os.path.join(ROOT, f)) < 200_000, f


def test_no_secrets_personal_paths_or_named_dubs():
    for f in files():
        text = open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read()
        for pattern in SECRETS:
            assert not re.search(pattern, text), f"{f}: {pattern}"
        for word in PERSONAL + UNNAMED:
            assert word not in text, f"{f}: {word}"


def test_the_repository_is_in_english():
    # Russian stays only where it is data: the table for Latin words in a Russian line, and its test.
    allowed = {"skills/anime-redub/scripts/dialogue.py", "tests/test_dialogue.py"}
    for f in files():
        text = open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read()
        if re.search(r"[\u0400-\u04ff]", text):
            assert f in allowed, f


def test_skill_text_has_nothing_a_launch_argument_could_replace():
    # Claude Code fills $0, $1 and so on in SKILL.md with the arguments, so a price written as "$1.50" would be corrupted.
    text = open(os.path.join(ROOT, "skills", "anime-redub", "SKILL.md"), encoding="utf-8").read()
    assert not re.search(r"\$\d|\$ARGUMENTS", text)


def test_the_pipeline_figure_matches_its_generator(tmp_path):
    source = open(os.path.join(ROOT, "docs", "make_pipeline.py"), encoding="utf-8").read()
    namespace = {"__name__": "figure", "__file__": str(tmp_path / "make_pipeline.py")}
    exec(source, namespace)
    for theme in ("light", "dark"):
        committed = open(os.path.join(ROOT, "docs", f"pipeline-{theme}.svg"), encoding="utf-8").read()
        assert committed == namespace["draw"](theme), theme


def test_env_file_is_ignored():
    r = subprocess.run(["git", "check-ignore", ".env", "x.mkv", "stems/vocals.wav"], cwd=ROOT, capture_output=True, text=True)
    assert len(r.stdout.splitlines()) == 3
