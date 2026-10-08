#!/usr/bin/env python3
"""Compile this project's simple singular PO catalogs; no external gettext install."""
import ast
import struct
from pathlib import Path

def compile_catalog(path):
    messages = {}
    msgid = msgstr = ''
    mode = None
    def save():
        if mode is not None:
            messages[msgid] = msgstr
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        if line.startswith(('msgctxt', 'msgid_plural', 'msgstr[')):
            raise ValueError('Use GNU gettext for contextual/plural catalogs; this helper is singular-only.')
        if line.startswith('msgid '):
            save()
            msgid = ast.literal_eval(line[6:])
            msgstr = ''
            mode = 'id'
        elif line.startswith('msgstr '):
            msgstr = ast.literal_eval(line[7:])
            mode = 'str'
        elif line.startswith('"'):
            value = ast.literal_eval(line)
            if mode == 'id':
                msgid += value
            else:
                msgstr += value
    save()
    pairs = sorted((k.encode(), v.encode()) for k, v in messages.items())
    n = len(pairs)
    offset = 28 + 16 * n
    ids = b''
    strs = b''
    id_table = []
    str_table = []
    for key, _ in pairs:
        id_table.append((len(key), offset + len(ids)))
        ids += key + b'\0'
    for _, value in pairs:
        str_table.append((len(value), offset + len(ids) + len(strs)))
        strs += value + b'\0'
    data = struct.pack('<7I', 0x950412DE, 0, n, 28, 28 + n * 8, 0, 0)
    data += b''.join(struct.pack('<2I', *p) for p in id_table + str_table) + ids + strs
    path.with_suffix('.mo').write_bytes(data)
    print(f'Compiled {path.relative_to(Path(__file__).resolve().parents[1])}: {n - 1} translations')

if __name__ == '__main__':
    for path in (Path(__file__).resolve().parents[1] / 'locale').glob('*/LC_MESSAGES/django.po'):
        compile_catalog(path)
