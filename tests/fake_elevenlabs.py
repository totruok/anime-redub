"""A local stand-in for the ElevenLabs API, so the whole pipeline can run without a paid call.

usage: fake_elevenlabs.py [PORT]    then set ELEVENLABS_API_URL=http://127.0.0.1:PORT

Speech is replaced by tone bursts, one pitch per voice, as long as the text would take.
It answers only the four routes the pipeline uses, and it remembers what each generated
audio file "says", so its recogniser can return the right words at the right times.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

SR = 44100
LETTERS_PER_SECOND = 14
GAP = 0.4


def burst(frequency, seconds):
    t = np.arange(int(seconds * SR)) / SR
    return (np.sin(2 * np.pi * frequency * t) * 0.2 * np.minimum(1, np.minimum(t, seconds - t) / 0.02)).astype(np.float32)


def to_mp3(x):
    with tempfile.TemporaryDirectory() as d:
        sf.write(os.path.join(d, "a.wav"), x, SR, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", os.path.join(d, "a.wav"), "-b:a", "128k", os.path.join(d, "a.mp3")], check=True)
        return open(os.path.join(d, "a.mp3"), "rb").read()


def frequency_of(voice_id):
    return 140 + int(hashlib.sha1(voice_id.encode()).hexdigest(), 16) % 500


class Handler(BaseHTTPRequestHandler):
    log = []
    heard = {}

    def log_message(self, *a):
        pass

    def reply(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        path = self.path.split("?")[0]
        Handler.log.append(path)
        if path == "/v1/text-to-voice/design":
            self.design(json.loads(raw))
        elif path == "/v1/text-to-voice":
            self.reply({"voice_id": "v_" + json.loads(raw)["generated_voice_id"]})
        elif path == "/v1/text-to-dialogue/with-timestamps":
            self.dialogue(json.loads(raw))
        elif path == "/v1/speech-to-text":
            self.scribe(raw)
        else:
            self.send_error(404)

    def design(self, body):
        # The language is taken from the description, the only place the real API can hear it from.
        code = "de" if "German" in body["voice_description"] else "es" if "Spanish" in body["voice_description"] else "en"
        seed = hashlib.sha1(body["voice_description"].encode()).hexdigest()
        previews = []
        for n in range(3):
            voice = f"{seed[:8]}_{n}"
            audio = to_mp3(burst(frequency_of(voice), 2.0))
            previews.append({"audio_base_64": base64.b64encode(audio).decode(), "generated_voice_id": voice, "duration_secs": 2.0, "language": code})
        self.reply({"text": body.get("text"), "previews": previews})

    def dialogue(self, body):
        pieces, words, segments, at = [], [], [], 0.0
        for n, item in enumerate(body["inputs"]):
            spoken = re.sub(r"\[[^\]]*\]", "", item["text"]).strip()
            seconds = max(0.4, len(spoken) / LETTERS_PER_SECOND)
            pieces += [burst(frequency_of(item["voice_id"]), seconds), np.zeros(int(GAP * SR), dtype=np.float32)]
            tokens = spoken.split() or [spoken]
            step = seconds / len(tokens)
            for t, token in enumerate(tokens):
                words.append({"text": token, "start": round(at + t * step, 3), "end": round(at + (t + 1) * step - 0.02, 3), "type": "word", "speaker_id": f"speaker_{item['voice_id']}"})
            segments.append({"voice_id": item["voice_id"], "dialogue_input_index": n})
            at += seconds + GAP
        audio = to_mp3(np.concatenate(pieces))
        Handler.heard[hashlib.sha1(audio).hexdigest()] = words
        self.reply({"audio_base64": base64.b64encode(audio).decode(), "voice_segments": segments})

    def scribe(self, raw):
        boundary = self.headers["Content-Type"].split("boundary=")[1].encode()
        form, audio = {}, b""
        for part in raw.split(b"--" + boundary)[1:-1]:
            head, _, body = part.partition(b"\r\n\r\n")
            body = body[:-2]  # the line break before the next boundary
            if b"filename=" in head:
                audio = body
            else:
                form[re.search(rb'name="([^"]+)"', head)[1].decode()] = body.decode()
        words = Handler.heard.get(hashlib.sha1(audio).hexdigest(), [{"text": "hola", "start": 0.0, "end": 0.5, "type": "word", "speaker_id": "speaker_0"}])
        self.reply({"language_code": form.get("language_code", "und"), "language_probability": 1.0, "words": words})


def start(port=0):
    """Start in the background and return the server. Its address is server.server_address."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler).serve_forever()
