"""Read-only deterministic Phase 2 CLI; no rendering/upload imports."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.beat_cloud import BeatCloud, DropboxTransport
from core.beat_fakes import MemoryDropbox
from core.beat_schema import instant
from core.beat_state import BeatState


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.add_argument("--now", required=True, help="ISO timestamp with offset")
    parser.add_argument("--tracks", required=True, help="JSON array: id, active")
    parser.add_argument("--config", help="Local config fixture; required for --fake")
    parser.add_argument("--state", help="Local state fixture (only --fake)")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report", action="append", default=[], metavar="CHANNEL=FILE",
                        help="Validated local channel report; repeat per channel")
    args = parser.parse_args()
    if (args.fake and not args.config) or (args.state and not args.fake):
        parser.error("--fake requires --config; --state requires --fake")
    now = instant(args.now)
    tracks = json.loads(Path(args.tracks).read_text(encoding="utf-8"))
    transport = MemoryDropbox() if args.fake else DropboxTransport.from_env()
    cloud = BeatCloud(transport)
    if args.fake and args.state:
        transport.files["/Soft Projects/Type Beat Generator/datos/beats/state.json"] = (Path(args.state).read_bytes(), "fixture")
    config = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else cloud.read("config")[0]
    reports = {}
    from core.beat_notion import read_report_file
    for spec in args.report:
        cid, separator, filename = spec.partition('=')
        if not separator or not cid or not filename or cid in reports:
            parser.error('--report requires unique CHANNEL=FILE')
        reports[cid] = read_report_file(filename)
    print(json.dumps(BeatState(cloud).dry_run(config, tracks, now, seed=args.seed, reports=reports),
                     sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
