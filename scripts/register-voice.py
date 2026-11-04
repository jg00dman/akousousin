#!/usr/bin/env python3
"""Generate opt-in Wine voice registration. Does not modify a Wine prefix."""
import argparse
import json
from pathlib import Path

CLSID = "{7C8B3F91-6F72-4C5B-A60F-2E895AB143D2}"
TOKEN = r"SOFTWARE\Microsoft\Speech\Voices\Tokens\Akousousin-Piper"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Piper model .onnx.json")
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--language", default="409", help="SAPI hexadecimal language ID")
    parser.add_argument("--make-default", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rate = args.sample_rate
    if args.config:
        rate = json.loads(args.config.read_text())["audio"]["sample_rate"]
    if not 8000 <= rate <= 192000 or not 1 <= args.port <= 65535:
        parser.error("sample rate or port outside supported range")
    if not args.language or any(c not in "0123456789abcdefABCDEF;" for c in args.language):
        parser.error("language must contain hexadecimal language IDs separated by semicolons")
    content = f'''Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\\{TOKEN}]
@="Piper (Akousousin)"
"CLSID"="{CLSID}"
"SampleRate"=dword:{rate:08x}
"Port"=dword:{args.port:08x}

[HKEY_LOCAL_MACHINE\\{TOKEN}\\Attributes]
"Name"="Piper (Akousousin)"
"Vendor"="Akousousin"
"Language"="{args.language}"
'''
    if args.make_default:
        token_id = ("HKEY_LOCAL_MACHINE\\" + TOKEN).replace("\\", "\\\\")
        content += f'''
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices]
"DefaultDefaultTokenId"="{token_id}"

[HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Speech\\Voices]
"DefaultTokenId"="{token_id}"
'''
    args.output.write_text(content, encoding="utf-16")


if __name__ == "__main__":
    main()
