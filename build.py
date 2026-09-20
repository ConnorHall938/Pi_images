#!/usr/bin/env python3
"""Build Raspberry Pi images with rpi-image-gen, and optionally flash them.

    ./build.py list                              show the available configs
    ./build.py build tv_image                    build -> output/tv_image.img
    ./build.py build tv_image --flash            ...then pick a disk from a list
    ./build.py build tv_image --flash /dev/sdb   ...then flash that disk
    ./build.py flash tv_image [/dev/sdb]         flash an image that is already built
    ./build.py clean tv_image                    remove the build tree for that config

A config called NAME is the file configs/<project>/config/NAME.yaml. Its project
folder (configs/<project>) is handed to rpi-image-gen as the source directory,
so layers, hooks and other files next to the config are found automatically.

Set RPI_IMAGE_GEN to the rpi-image-gen executable if it is not at ../rpi-image-gen.
Add --dry-run (before the command) to print what would run without doing it.
"""
import argparse
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIGS_DIR = ROOT / "configs"
BUILD_DIR = ROOT / "build"
OUTPUT_DIR = ROOT / "output"
RPI_IMAGE_GEN = Path(
    os.environ.get("RPI_IMAGE_GEN", ROOT.parent / "rpi-image-gen" / "rpi-image-gen")
)

# A disk with any of these mounted is the machine we are running on: never a target.
SYSTEM_MOUNTS = {"/", "/boot", "/boot/firmware"}

dry_run = False


class ScriptError(Exception):
    """A problem worth telling the user about, without a traceback."""


# --- running commands ---------------------------------------------------------


def run(cmd):
    """Run a command that changes something. Only prints it under --dry-run."""
    print("$ " + shlex.join(str(part) for part in cmd), flush=True)
    if not dry_run:
        subprocess.run([str(part) for part in cmd], check=True)


def capture(cmd, cwd=None):
    """Run a read-only command and return its output. Always runs, even in a dry run."""
    result = subprocess.run(
        [str(part) for part in cmd],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        raise ScriptError(f"{shlex.join(str(p) for p in cmd)} failed:\n{result.stdout}")
    return result.stdout


# --- configs ------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    name: str  # what you type, e.g. tv_image
    file: Path  # configs/<project>/config/<name>.yaml
    project_dir: Path  # configs/<project>, passed to rpi-image-gen as -S

    @property
    def output_image(self):
        return OUTPUT_DIR / f"{self.name}.img"


def discover_configs():
    return [
        Config(path.stem, path, path.parent.parent)
        for path in sorted(CONFIGS_DIR.glob("*/config/*.yaml"))
    ]


def find_config(name):
    name = name.removesuffix(".yaml")
    configs = discover_configs()
    matches = [c for c in configs if c.name == name]
    if len(matches) == 1:
        return matches[0]
    if matches:
        paths = "\n  ".join(str(c.file.relative_to(ROOT)) for c in matches)
        raise ScriptError(f"'{name}' is ambiguous, found in:\n  {paths}")
    available = ", ".join(c.name for c in configs) or "none"
    raise ScriptError(f"no config called '{name}' (available: {available})")


# --- rpi-image-gen ------------------------------------------------------------


def check_rpi_image_gen():
    if not RPI_IMAGE_GEN.is_file():
        raise ScriptError(
            f"rpi-image-gen not found at {RPI_IMAGE_GEN} (set RPI_IMAGE_GEN to its path)"
        )


def rig_args(config):
    """The options every rpi-image-gen command needs to find this config."""
    return ["-S", config.project_dir, "-c", config.file.name, "-B", BUILD_DIR]


def image_name(config):
    """The image name the config resolves to (includes and overrides applied)."""
    rig_dir = RPI_IMAGE_GEN.parent
    output = capture(
        [rig_dir / "bin" / "ig", "config", "-S", config.project_dir, config.file],
        cwd=rig_dir,  # ig looks for its built-in configs relative to here
    )
    for line in output.splitlines():
        if line.startswith("CFG IGconf_image_name="):
            return line.split("=", 1)[1].strip()
    raise ScriptError(f"could not work out the image name for '{config.name}'")


def find_built_image(config, started_at):
    """The newest <image name>.img under the build dir, and it must be from this build."""
    name = image_name(config)
    found = sorted(BUILD_DIR.rglob(f"{name}.img"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise ScriptError(f"{name}.img not found under {BUILD_DIR}")
    newest = found[-1]
    if newest.stat().st_mtime < started_at:
        raise ScriptError(f"{newest} is older than this build; the build produced no image")
    return newest


def build(config):
    """Build the image, move it to output/<name>.img and return that path."""
    check_rpi_image_gen()
    started_at = time.time()
    if not dry_run:
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
    run([RPI_IMAGE_GEN, "build", *rig_args(config)])
    if dry_run:
        return config.output_image
    built = find_built_image(config, started_at)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # A move is instant on the same disk; a copy of a multi-GB image takes minutes.
    # Every build regenerates the image, so nothing needs it left in build/.
    print(f"moving {built} -> {config.output_image}", flush=True)
    shutil.move(built, config.output_image)
    return config.output_image


def clean(config):
    check_rpi_image_gen()
    run([RPI_IMAGE_GEN, "clean", *rig_args(config)])


# --- disks --------------------------------------------------------------------


@dataclass(frozen=True)
class Disk:
    path: str
    size: int
    model: str
    transport: str
    removable: bool
    holds_system: bool

    def describe(self):
        gib = self.size / 1024**3
        return f"{self.path:<12} {gib:7.1f} GiB  {self.model or 'unknown model'}  ({self.transport or 'no transport info'})"


def holds_system(path):
    """True if the disk, or any partition on it, is mounted somewhere the system needs."""
    mounts = capture(["lsblk", "-nro", "MOUNTPOINT", path]).splitlines()
    return any(mount.strip() in SYSTEM_MOUNTS for mount in mounts)


def read_disks():
    output = capture(
        ["lsblk", "--json", "--bytes", "--output",
         "PATH,SIZE,TYPE,RM,HOTPLUG,TRAN,MODEL"]
    )
    disks = []
    for device in json.loads(output)["blockdevices"]:
        if device.get("type") != "disk":
            continue
        disks.append(
            Disk(
                path=device["path"],
                size=int(device["size"]),
                model=(device.get("model") or "").strip(),
                transport=device.get("tran") or "",
                removable=bool(device.get("rm") or device.get("hotplug")
                               or device.get("tran") == "usb"),
                holds_system=holds_system(device["path"]),
            )
        )
    return disks


def choose_disk():
    """Show a numbered list of safe target disks and return the one picked."""
    disks = read_disks()
    for disk in disks:
        if disk.holds_system:
            print(f"(not offered: {disk.path} holds the running system)")
    candidates = [d for d in disks if d.removable and not d.holds_system]
    if not candidates:
        raise ScriptError("no removable disks found - plug in the card or drive and try again")
    if not sys.stdin.isatty():
        raise ScriptError("no device given and not running interactively; pass a device path")

    print("Flash to which disk? Everything on it will be erased.")
    for number, disk in enumerate(candidates, start=1):
        print(f"  {number}) {disk.describe()}")
    while True:
        answer = input(f"Enter a number 1-{len(candidates)}, or q to quit: ").strip().lower()
        if answer in ("q", "quit"):
            raise ScriptError("cancelled")
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1].path
        print("Not a valid choice.")


def check_target(path, image_size, allow_fixed):
    """Refuse anything that is not a safe flash target. Returns the Disk if it is."""
    path = os.path.realpath(path)  # /dev/disk/by-id/... -> /dev/sdX
    if not os.path.exists(path):
        raise ScriptError(f"{path} does not exist")
    if not stat.S_ISBLK(os.stat(path).st_mode):
        raise ScriptError(f"{path} is not a block device")
    disks = {d.path: d for d in read_disks()}
    if path not in disks:
        raise ScriptError(f"{path} is not a whole disk (use /dev/sdX, not /dev/sdX1)")
    disk = disks[path]
    if disk.holds_system:
        raise ScriptError(f"{path} holds the running system (/ or /boot). Refusing.")
    if not disk.removable and not allow_fixed:
        raise ScriptError(f"{path} does not look removable; pass --allow-fixed if you are sure")
    if image_size and disk.size < image_size:
        raise ScriptError(f"{path} is smaller than the image ({disk.size} < {image_size} bytes)")
    return disk


def select_target(requested, allow_fixed):
    """Turn the --flash argument ('' = pick from a list) into a checked disk path."""
    path = requested or choose_disk()
    return check_target(path, image_size=0, allow_fixed=allow_fixed).path


def unmount_partitions(disk_path):
    for line in capture(["lsblk", "-nro", "PATH,MOUNTPOINT", disk_path]).splitlines():
        part, _, mountpoint = line.partition(" ")
        if mountpoint in SYSTEM_MOUNTS:
            raise ScriptError(f"refusing to unmount {mountpoint}: it is part of the running system")
        if mountpoint.startswith("/"):  # skips "[SWAP]" and empty entries
            run(["sudo", "umount", part])


def flash(image, disk_path, allow_fixed):
    """Write the image to the disk. Checks it again, as a long build can change things."""
    if not dry_run and not image.is_file():
        raise ScriptError(f"{image} not found - build it first")
    size = image.stat().st_size if image.is_file() else 0
    disk = check_target(disk_path, size, allow_fixed)
    print(f"Flashing {image.name} to {disk.describe()}", flush=True)
    unmount_partitions(disk.path)
    run(["sudo", "dd", f"if={image}", f"of={disk.path}", "bs=4M", "conv=fsync", "status=progress"])
    run(["sync"])
    print(f"done - safe to remove {disk.path}")


# --- commands -----------------------------------------------------------------


def cmd_list(args):
    configs = discover_configs()
    if not configs:
        print(f"no configs found in {CONFIGS_DIR}/<project>/config/")
    for config in configs:
        print(f"{config.name:<20} {config.file.relative_to(ROOT)}")


def cmd_build(args):
    config = find_config(args.config)
    target = None
    if args.flash is not None:
        target = select_target(args.flash, args.allow_fixed)  # choose now, not after the build
    image = build(config)
    if target:
        flash(image, target, args.allow_fixed)


def cmd_flash(args):
    config = find_config(args.config)
    target = select_target(args.device or "", args.allow_fixed)
    flash(config.output_image, target, args.allow_fixed)


def cmd_clean(args):
    clean(find_config(args.config))


# --- command line -------------------------------------------------------------


def device_path(value):
    if value and not value.startswith("/dev/"):
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a device path (put --flash last, or give it /dev/sdX)"
        )
    return value


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Build Raspberry Pi images with rpi-image-gen, and optionally flash them."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands that would change something, and don't run them")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="show the available configs")
    listing.set_defaults(func=cmd_list)

    building = commands.add_parser("build", help="build a config")
    building.add_argument("config", help="config name, e.g. tv_image")
    building.add_argument("--flash", nargs="?", const="", type=device_path, metavar="DEVICE",
                          help="flash afterwards; without DEVICE, pick from a list")
    building.add_argument("--allow-fixed", action="store_true",
                          help="allow flashing a disk that does not look removable")
    building.set_defaults(func=cmd_build)

    flashing = commands.add_parser("flash", help="flash an image that is already built")
    flashing.add_argument("config", help="config name, e.g. tv_image")
    flashing.add_argument("device", nargs="?", type=device_path,
                          help="target disk; omit to pick from a list")
    flashing.add_argument("--allow-fixed", action="store_true",
                          help="allow flashing a disk that does not look removable")
    flashing.set_defaults(func=cmd_flash)

    cleaning = commands.add_parser("clean", help="remove the build tree for a config")
    cleaning.add_argument("config", help="config name, e.g. tv_image")
    cleaning.set_defaults(func=cmd_clean)

    return parser.parse_args(argv)


def main(argv=None):
    global dry_run
    args = parse_args(argv)
    dry_run = args.dry_run
    try:
        args.func(args)
    except ScriptError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as err:
        print(f"error: command failed with exit code {err.returncode}", file=sys.stderr)
        return err.returncode or 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
