import tarfile, gzip, shutil
from pathlib import Path

proj = Path('.')
tar = proj / 'node20.tar.xz'

if not tar.exists():
    print("FAIL: node20.tar.xz not found")
    raise SystemExit(1)

print("Extracting...")
with tarfile.open(tar) as t:
    t.extractall(proj)

node_bin = proj / 'node-v20.18.0-linux-x64' / 'bin' / 'node'
if not node_bin.exists():
    print("FAIL: node binary not in archive")
    raise SystemExit(1)

print("Node 20 binary: {:,} bytes".format(node_bin.stat().st_size))

if open(node_bin, 'rb').read(4) != b'\x7fELF':
    print("FAIL: not ELF binary")
    raise SystemExit(1)
print("ELF verified")

print("Compressing...")
gz = proj / 'nodejs' / 'node.gz'
if gz.exists():
    gz.unlink()

with open(node_bin, 'rb') as fin, gzip.open(gz, 'wb', compresslevel=9) as fout:
    shutil.copyfileobj(fin, fout)

size = gz.stat().st_size
print("New node.gz: {:,} bytes ({:.1f} MB)".format(size, size / 1024 / 1024))

if gzip.open(gz, 'rb').read(4) != b'\x7fELF':
    print("FAIL: gz content corrupt")
    raise SystemExit(1)
print("gz verified")

print("Cleaning up...")
shutil.rmtree(proj / 'node-v20.18.0-linux-x64', ignore_errors=True)
tar.unlink(missing_ok=True)
print("DONE — ready to commit")