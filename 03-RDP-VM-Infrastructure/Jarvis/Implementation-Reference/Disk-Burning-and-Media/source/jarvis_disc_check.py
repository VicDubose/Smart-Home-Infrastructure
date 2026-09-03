#!/usr/bin/env python3

import subprocess
import json


DEVICE = "/dev/sr0"


def run(cmd):
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


def main():
    print("===== JARVIS DISC TYPE CHECK =====")
    print(f"Device: {DEVICE}")
    print("")

    # Basic block/device metadata
    code, lsblk_out = run([
        "lsblk",
        "-J",
        "-o",
        "NAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,TRAN",
        DEVICE,
    ])

    print("===== LSBLK CHECK =====")
    print(lsblk_out)
    print("")

    fstype = None
    label = None

    try:
        data = json.loads(lsblk_out)
        dev = data["blockdevices"][0]
        fstype = dev.get("fstype")
        label = dev.get("label")
    except Exception:
        pass

    print(f"Detected filesystem: {fstype}")
    print(f"Detected label: {label}")
    print("")

    # DVD-Video check
    print("===== DVD-VIDEO CHECK =====")
    dvd_code, dvd_out = run(["dvdbackup", "-I", "-i", DEVICE])

    if "DVD-Video information" in dvd_out or "VIDEO_TS" in dvd_out:
        print("Detected: DVD-Video")
        if "DVD with title" in dvd_out:
            for line in dvd_out.splitlines():
                if "DVD with title" in line:
                    print(line.strip())
        print("")
        print("Recommended workflow:")
        print("  Use Jarvis DVD ingest workflow.")
        return
    else:
        print("Not detected as DVD-Video.")
        print("")

    # Audio CD check
    print("===== AUDIO CD CHECK =====")
    cd_code, cd_out = run(["cd-discid", DEVICE])

    if cd_code == 0 and cd_out:
        print("Detected: Audio CD")
        print(cd_out)
        print("")
        print("Recommended workflow:")
        print("  Use Jarvis CD/music ingest workflow.")
        return
    else:
        print("Not detected as standard Audio CD.")
        print(cd_out)
        print("")

    # Data/filesystem disc fallback
    print("===== FINAL CLASSIFICATION =====")

    if fstype in ["udf", "iso9660"]:
        print("Detected: Data/filesystem optical disc")
        print(f"Filesystem: {fstype}")
        print(f"Label: {label}")
        print("")
        print("Recommended workflow:")
        print("  Mount/copy/archive workflow, not Audio CD ripping.")
    else:
        print("Detected: Unknown/unreadable optical media")
        print("Recommended workflow:")
        print("  Stop and inspect manually.")


if __name__ == "__main__":
    main()
