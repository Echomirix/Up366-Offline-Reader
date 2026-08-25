#!/usr/bin/env python3
"""Extract the U3ENC AES key from up366.exe and decrypt .u3enc files."""

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CIPHER_PATTERN = b'createDecipheriv("aes-128-cbc"'
KEY_MARKER = b'Buffer.from("'


def extract_key(exe_path):
    data = exe_path.read_bytes()
    pos = data.find(CIPHER_PATTERN)
    if pos < 0:
        raise ValueError(f'createDecipheriv("aes-128-cbc") not found in {exe_path}')

    window = data[max(0, pos - 2048):pos]
    marker_pos = window.rfind(KEY_MARKER)
    if marker_pos < 0:
        raise ValueError('Buffer.from("<key>", "base64") not found before createDecipheriv')

    token_start = marker_pos + len(KEY_MARKER)
    token_end = window.find(b'"', token_start)
    if token_end < 0:
        raise ValueError('unterminated base64 key string')

    key_b64 = window[token_start:token_end].decode('utf-8')
    key = base64.b64decode(key_b64)
    if len(key) != 16:
        raise ValueError(f'unexpected key length {len(key)}, expected 16 for aes-128')

    return key_b64, key, pos


def decrypt_u3enc(data, key):
    if len(data) < 32:
        raise ValueError('file too short: need at least 16-byte IV + one AES block')

    iv = data[:16]
    ciphertext = data[16:]
    if len(ciphertext) % 16 != 0:
        raise ValueError('ciphertext length is not a multiple of 16')

    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='U3ENC key extractor/decryptor for up366.exe'
    )
    sub = parser.add_subparsers(dest='command', required=True)

    ex = sub.add_parser('extract-key', help='extract the hardcoded AES key from an exe')
    ex.add_argument('exe', type=Path, help='path to up366.exe')

    de = sub.add_parser('decrypt', help='extract key from an exe and decrypt a .u3enc file')
    de.add_argument('--exe', type=Path, help='path to up366.exe (unless --key-hex is used)')
    de.add_argument('input', type=Path, help='path to the .u3enc file')
    de.add_argument('output', type=Path, nargs='?', help='output path (default: input without .u3enc)')
    de.add_argument('--key-hex', help='use this 32-char hex AES-128 key instead of extracting from exe')

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.command == 'extract-key':
        key_b64, key, offset = extract_key(args.exe)
        print(f'key base64: {key_b64}')
        print(f'key hex:    {key.hex()}')
        print(f'cipher ref: file offset {offset}')
        return

    if args.command == 'decrypt':
        if args.key_hex:
            key = bytes.fromhex(args.key_hex)
            if len(key) != 16:
                raise ValueError('--key-hex must be 32 hex chars (16 bytes)')
            key_b64 = base64.b64encode(key).decode()
            offset = None
        else:
            if args.exe is None:
                raise ValueError('decrypt requires --exe or --key-hex')
            key_b64, key, offset = extract_key(args.exe)

        data = args.input.read_bytes()
        plain = decrypt_u3enc(data, key)

        output = args.output
        if output is None:
            name = args.input.name
            output = args.input.with_name(
                name[:-6] if name.lower().endswith('.u3enc') else name + '.dec'
            )
        output.write_bytes(plain)

        print(f'key base64: {key_b64}')
        print(f'key hex:    {key.hex()}')
        if offset is not None:
            print(f'cipher ref: file offset {offset}')
        print(f'iv:         {data[:16].hex()}')
        print(f'plaintext:  {len(plain)} bytes -> {output}')
        return

    raise SystemExit('unknown command')


if __name__ == '__main__':
    main()
