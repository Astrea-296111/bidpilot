import argparse
import asyncio
import json
from pathlib import Path

from bidpilot.config import Settings
from bidpilot.service import BidPilotService


async def demo(args):
    settings = Settings(mode="lite", embedding_provider="hash")
    async with BidPilotService(settings) as service:
        path = Path(args.fixture).resolve()
        tender = await service.repository.create_tender(path.stem, path)
        report = await service.analyze(tender.id)
        print(
            json.dumps(
                {
                    "project": report["project_name"],
                    "decision": report["decision"],
                    "status": report["status"],
                    "metrics": report["metrics"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if report["approval_required"]:
            approve = args.approve
            if not args.approve and not args.reject:
                approve = input("Save this simulated opportunity? [y/N]: ").strip().lower() == "y"
            report = await service.analyze(tender.id, approval=approve)
        output = settings.project_root / "artifacts/demo"
        output.mkdir(parents=True, exist_ok=True)
        destination = output / f"{path.stem}-report.json"
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Final status: {report['status']}; report: {destination}")


def main():
    parser = argparse.ArgumentParser(description="BidPilot runnable offline demo")
    sub = parser.add_subparsers(dest="command", required=True)
    demo_parser = sub.add_parser("demo")
    demo_parser.add_argument("--fixture", default="data/rfps/01-bank-data-platform.md")
    group = demo_parser.add_mutually_exclusive_group()
    group.add_argument(
        "--approve", action="store_true", help="Explicitly approve saving simulated opportunity"
    )
    group.add_argument("--reject", action="store_true", help="Reject opportunity persistence")
    args = parser.parse_args()
    asyncio.run(demo(args))


if __name__ == "__main__":
    main()
