"""Create the SideStore/AltStore source file (source.json) for a VANTA app release."""

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--build", required=True)
    p.add_argument("--bundle-id", required=True)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    base = f"https://github.com/{a.repo}"
    raw = f"https://raw.githubusercontent.com/{a.repo}/main"
    source = {
        "name": "VANTA",
        "identifier": f"{a.bundle_id}.source",
        "sourceURL": f"{base}/releases/latest/download/source.json",
        "website": base,
        "iconURL": f"{raw}/assets/icons/ios/AppIcon~ios-marketing.png",
        "apps": [
            {
                "name": "VANTA",
                "bundleIdentifier": a.bundle_id,
                "developerName": "VANTA",
                "subtitle": "Proaktiver persönlicher Assistent",
                "localizedDescription": "VANTA App, automatisch gebaut aus dem Repository.",
                "iconURL": f"{raw}/assets/icons/ios/AppIcon~ios-marketing.png",
                "tintColor": "4F46E5",
                "versions": [
                    {
                        "version": a.version,
                        "buildVersion": a.build,
                        "date": a.date,
                        "localizedDescription": f"Build {a.build}",
                        "downloadURL": f"{base}/releases/download/{a.tag}/VANTA.ipa",
                        "size": a.size,
                        "minOSVersion": "17.0",
                    }
                ],
            }
        ],
        "news": [],
    }
    Path(a.out).write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
