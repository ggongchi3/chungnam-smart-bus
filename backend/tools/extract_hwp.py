"""Read unencrypted HWP 5 paragraph text without executing embedded content."""
import struct
import sys
import zlib
from pathlib import Path


def extract(path):
    blob = Path(path).read_bytes()
    if blob[:8] != bytes.fromhex('d0cf11e0a1b11ae1'):
        raise ValueError('Not an OLE HWP file')
    size = 1 << struct.unpack_from('<H', blob, 30)[0]
    def sector(index):
        return blob[(index + 1) * size:(index + 2) * size]
    fat = []
    for index in struct.unpack_from('<109I', blob, 76):
        if index < 0xFFFFFFFA:
            fat.extend(struct.unpack('<' + str(size // 4) + 'I', sector(index)))
    def chain(index, table, reader):
        result, seen = b'', set()
        while index < 0xFFFFFFFA:
            if index in seen:
                raise ValueError('Cyclic OLE chain')
            seen.add(index)
            result += reader(index)
            index = table[index]
        return result
    directory = chain(struct.unpack_from('<I', blob, 48)[0], fat, sector)
    entries = {}
    for offset in range(0, len(directory), 128):
        entry = directory[offset:offset + 128]
        if entry[66]:
            name = entry[:struct.unpack_from('<H', entry, 64)[0] - 2].decode('utf-16le')
            entries[name] = (struct.unpack_from('<I', entry, 116)[0], struct.unpack_from('<Q', entry, 120)[0])
    root, root_length = entries['Root Entry']
    mini_stream = chain(root, fat, sector)[:root_length]
    mini_raw = chain(struct.unpack_from('<I', blob, 60)[0], fat, sector)
    mini_fat = struct.unpack('<' + str(len(mini_raw) // 4) + 'I', mini_raw)
    def stream(name):
        start, length = entries[name]
        if length < 4096:
            return chain(start, mini_fat, lambda i: mini_stream[i * 64:(i + 1) * 64])[:length]
        return chain(start, fat, sector)[:length]
    flags = struct.unpack_from('<I', stream('FileHeader'), 36)[0]
    if flags & 2:
        raise ValueError('Encrypted HWP is unsupported')
    paragraphs = []
    for name in sorted(entries):
        if not name.startswith('Section'):
            continue
        body = stream(name)
        if flags & 1:
            body = zlib.decompress(body, -15)
        offset = 0
        while offset < len(body):
            header = struct.unpack_from('<I', body, offset)[0]
            offset += 4
            tag, length = header & 1023, header >> 20
            if length == 4095:
                length = struct.unpack_from('<I', body, offset)[0]
                offset += 4
            data = body[offset:offset + length]
            offset += length
            if tag == 67:
                words, i = [], 0
                while i + 1 < len(data):
                    code = struct.unpack_from('<H', data, i)[0]
                    if code in (9, 10, 13):
                        words.append(' ' if code == 9 else '\n')
                        i += 16 if code == 9 else 2
                    elif code < 32:
                        i += 16 if code in (1,2,3,11,12,14,15,16,17,18,21,22,23) else 2
                    else:
                        words.append(chr(code))
                        i += 2
                paragraphs.append(''.join(words))
    return '\n'.join(paragraphs)


if __name__ == '__main__':
    result = extract(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(result, encoding='utf-8')
    else:
        print(result)
