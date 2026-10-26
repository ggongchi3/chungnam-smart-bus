"""Local-only demo control. No management API and no destructive reset."""
import argparse
import json
from uuid import uuid4

from backend.config import ROOT
from backend.integrations.providers import SCENARIOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['scenario'])
    parser.add_argument('--name', choices=SCENARIOS, required=True)
    args = parser.parse_args()
    path = ROOT / '.local/scenario.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps({'scenario': args.name, 'revision': uuid4().hex}), encoding='utf-8')
    pending.replace(path)
    print('Demo scenario:', args.name)


if __name__ == '__main__':
    main()
