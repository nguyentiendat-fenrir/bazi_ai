"""Synthetic RAR3 stored files, never copied from proprietary source/books.

Format reference: https://www.rarlab.com/technote.htm (RAR 4.x headers).
The reader under test is rarfile, independent of this small fixture writer.
"""
import struct
import zlib


def header(kind, flags, body):
    content = struct.pack('<BHH', kind, flags, 7 + len(body)) + body
    return struct.pack('<H', zlib.crc32(content) & 0xffff) + content


def make_rar(entries):
    """Entries: (name, bytes[, unix_mode[, flags]]). Deterministic bytes."""
    result = b'Rar!\x1a\x07\x00' + header(0x73, 0, b'\x00' * 6)
    for entry in entries:
        name, data = entry[:2]
        mode = entry[2] if len(entry) > 2 else 0o100644
        flags = entry[3] if len(entry) > 3 else 0x8000
        encoded = name.encode('utf-8')
        flags |= 0x200  # UTF-8 filename
        if mode & 0o170000 == 0o040000:
            flags |= 0xe0
        body = struct.pack('<IIBIIBBHI', len(data), len(data), 3,
                           zlib.crc32(data), 0x50210000, 20, 0x30,
                           len(encoded), mode) + encoded
        result += header(0x74, flags, body) + data
    return result + header(0x7b, 0, b'')
