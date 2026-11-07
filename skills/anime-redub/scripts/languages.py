"""The languages a dub can be made in.

usage: languages.py        prints every code and name

The list comes from the ElevenLabs model page for eleven_v4, read in November 2026. Most
codes are ISO 639-1; ast, yue, ceb, fil, kam and ckb are ISO 639-3. The ElevenLabs reference
says a code the model does not support is ignored, which this repository has not tested,
so a typo is stopped here, before anything is paid for. If the documentation lists a new
language, add it below.
"""

LANGUAGES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese", "ast": "Asturian", "az": "Azerbaijani",
    "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali", "bs": "Bosnian", "ca": "Catalan", "ceb": "Cebuano",
    "ckb": "Sorani Kurdish", "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German", "el": "Greek",
    "en": "English", "es": "Spanish", "et": "Estonian", "fa": "Persian", "ff": "Fula", "fi": "Finnish",
    "fil": "Filipino", "fr": "French", "gl": "Galician", "gu": "Gujarati", "ha": "Hausa", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian", "is": "Icelandic",
    "it": "Italian", "ja": "Japanese", "jv": "Javanese", "ka": "Georgian", "kam": "Kamba", "kk": "Kazakh",
    "kn": "Kannada", "ko": "Korean", "ky": "Kyrgyz", "lb": "Luxembourgish", "lg": "Luganda", "ln": "Lingala",
    "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese", "my": "Burmese", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "oc": "Occitan", "or": "Odia", "pa": "Punjabi", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sd": "Sindhi", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sr": "Serbian", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai", "tr": "Turkish", "uk": "Ukrainian",
    "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "wo": "Wolof", "yue": "Cantonese", "zh": "Mandarin Chinese",
    "zu": "Zulu",
}


def check(code):
    """The English name of a language code. An unknown code stops the run before anything is paid for."""
    if code not in LANGUAGES:
        raise SystemExit(f"unknown language code {code!r}. Run languages.py for the list, for example: en, es, de, fr, ja, ko, zh, pt, ru")
    return LANGUAGES[code]


def main():
    for code, name in sorted(LANGUAGES.items()):
        print(f"{code:<4} {name}")


if __name__ == "__main__":
    main()
