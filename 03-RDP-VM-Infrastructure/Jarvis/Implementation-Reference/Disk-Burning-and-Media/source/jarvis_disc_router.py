#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
from pathlib import Path


DEVICE = "/dev/sr0"


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def detect_disc(device):
    info = {
        "device": device,
        "disc_type": "unknown",
        "fstype": None,
        "label": None,
        "dvd_title": None,
        "reason": [],
    }

    code, lsblk_out = run_cmd([
        "lsblk", "-J",
        "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,TRAN",
        device,
    ])

    try:
        data = json.loads(lsblk_out)
        dev = data["blockdevices"][0]
        info["fstype"] = dev.get("fstype")
        info["label"] = dev.get("label")
    except Exception as e:
        info["reason"].append(f"lsblk_parse_failed: {e}")

    dvd_code, dvd_out = run_cmd(["dvdbackup", "-I", "-i", device])

    if "DVD-Video information" in dvd_out or "VIDEO_TS" in dvd_out:
        info["disc_type"] = "dvd_video"

        match = re.search(r'DVD with title "([^"]+)"', dvd_out)
        if match:
            info["dvd_title"] = match.group(1)

        info["reason"].append("dvdbackup_detected_dvd_video")
        return info

    cd_code, cd_out = run_cmd(["cd-discid", device])

    if cd_code == 0 and cd_out:
        info["disc_type"] = "audio_cd"
        info["reason"].append("cd_discid_detected_audio_cd")
        return info

    if info["fstype"] in ["udf", "iso9660"]:
        info["disc_type"] = "data_or_filesystem_disc"
        info["reason"].append(f"filesystem_detected_{info['fstype']}")
        return info

    return info


def main():
    parser = argparse.ArgumentParser(description="Jarvis optical disc router.")
    parser.add_argument("--device", default=DEVICE)
    parser.add_argument("--show", default=None)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--disc", type=int, default=None)
    parser.add_argument("--ai", default="llama3:8b")
    parser.add_argument("--library", default="/mnt/media/Shows")
    args = parser.parse_args()

    print("===== JARVIS DISC ROUTER =====")
    print(f"Device: {args.device}")
    print("")

    info = detect_disc(args.device)

    print("===== DISC DETECTION =====")
    print(f"Type: {info['disc_type']}")
    print(f"Filesystem: {info['fstype']}")
    print(f"Label: {info['label']}")
    print(f"DVD title: {info['dvd_title']}")
    print(f"Reason: {', '.join(info['reason'])}")
    print("")

    if info["disc_type"] == "dvd_video":
        if args.show and args.season and args.disc:
            print("Routing: TV/DVD episode workflow")
            cmd = [
                "python3",
                str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"),
                "--show", args.show,
                "--season", str(args.season),
                "--disc", str(args.disc),
                "--ai", args.ai,
            ]
            print("")
            print("$ " + " ".join(cmd))
            subprocess.run(cmd)
            return

        print("Routing: Generic DVD-Video workflow")
        print("")
        print("This is a DVD-Video, but no --show/--season/--disc was provided.")
        print("Jarvis will not force it into the TV episode workflow.")
        print("")
        print("Recommended command:")
        print("  python3 ~/rdp-scripts/Jarvis/media/jarvis_generic_dvd_ingest.py --dry-run")
        print("")
        print("Run without --dry-run after reviewing the classification.")
        return

    if info["disc_type"] == "audio_cd":
        print("Routing: Audio CD workflow")
        print("")
        print("Next command:")
        print("  python3 ~/rdp-scripts/Jarvis/media/jarvis_cd_ingest.py --format flac")
        print("")
        print("Note: jarvis_cd_ingest.py still needs to be built.")
        return

    if info["disc_type"] == "data_or_filesystem_disc":
        print("Routing: Data/filesystem disc workflow")
        print("")
        print("Recommended next commands:")
        print("  sudo mkdir -p /mnt/disc")
        print(f"  sudo mount {args.device} /mnt/disc")
        print("  find /mnt/disc -maxdepth 3 -type f | sort | head -100")
        return

    print("Routing: UNKNOWN")
    print("Jarvis cannot safely classify this disc. Manual inspection required.")


if __name__ == "__main__":
    main()
