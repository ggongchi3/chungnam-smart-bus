"""Compare project files outside backend against the recorded initial hashes."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    baseline = json.loads((root/'backend/docs/workspace-baseline.json').read_text(encoding='utf-8'))
    current = {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in root.rglob('*') if p.is_file() and
               p.relative_to(root).parts[0] not in ('backend','.git')}
    before = baseline['outsideBackend']
    changed = sorted(k for k in before.keys() | current.keys() if before.get(k) != current.get(k))
    tracked = subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
    assert not changed, changed
    assert all(p.startswith('backend/') for p in tracked + untracked)
    report = {'branchBefore':baseline['branchBefore'], 'statusBefore':baseline['statusBefore'],
              'branchAfter':subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip(),
              'outsideFileCount':len(current), 'outsideChanges':changed,
              'trackedChanges':tracked,'newFiles':untracked,'remoteActions':[]}
    (root/'backend/docs/workspace-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Outside backend: {len(current)} files unchanged; tracked changes {len(tracked)}, new files {len(untracked)}')


if __name__ == '__main__':
    main()
