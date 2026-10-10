#!/usr/bin/env python3
"""Build Raspberry Pi images with rpi-image-gen, and optionally flash them.

    ./build.py list                              show the available configs
    ./build.py build build_host                  build -> output/build_host.img
    ./build.py build build_host --flash          ...then pick a disk from a list
    ./build.py build build_host --flash /dev/sdb ...then flash that disk
    ./build.py flash build_host [/dev/sdb]       flash an image that is already built
                                                 (add --no-env to leave the secrets off)
    ./build.py flash-image ~/Downloads/build_host.zip [/dev/sdb]
                                                 flash an image from elsewhere, eg from CI:
                                                 .img, .img.xz, or the run's artifact .zip
    ./build.py clean build_host                  remove the build tree for that config

This repository is one rpi-image-gen source tree, laid out like rpi-image-gen itself:

    config/NAME.yaml       a config, built with `./build.py build NAME`
    layer/                 layers: shared ones in layer/shared/, others per image
    resources/             files a config puts in the image, as ${@SRCROOT}/resources/...
    environment/           local keys and secrets (ssh.pub, *.psk, tokens), git-ignored.
                           Secrets are not built into images: flashing copies the files
                           a config lists under bootenv: files: onto the card's boot
                           partition, and the bootenv layer moves them into place at boot.

The repository root is handed to rpi-image-gen as the source directory (-S), so its
layers and config are found automatically, alongside rpi-image-gen's own.

rpi-image-gen is a git submodule (rpi-image-gen/). After a fresh clone, fetch it with
`git submodule update --init`; set RPI_IMAGE_GEN to use a different checkout instead.
Add --dry-run (before the command) to print what would run without doing it.
"""
import argparse
import contextlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT  # passed to rpi-image-gen as -S
CONFIG_DIR = ROOT / "config"
BUILD_DIR = ROOT / "build"
OUTPUT_DIR = ROOT / "output"
ENV_DIR = ROOT / "environment"
BOOT_ENV_DIR = "environment"  # on the card's boot partition, where the bootenv layer looks
USING_SUBMODULE = "RPI_IMAGE_GEN" not in os.environ
RPI_IMAGE_GEN = Path(
    os.environ.get("RPI_IMAGE_GEN", ROOT / "rpi-image-gen" / "rpi-image-gen")
)

# A disk with any of these mounted is the machine we are running on: never a target.
SYSTEM_MOUNTS = {"/", "/boot", "/boot/firmware"}

dry_run = False


class ScriptError(Exception):
    """A problem worth telling the user about, without a traceback."""


# --- running commands ---------------------------------------------------------


@contextlib.contextmanager
def timed(label):
    """Print how long the enclosed steps took."""
    started = time.monotonic()
    try:
        yield
    finally:
        seconds = int(time.monotonic() - started)
        print(f"[time] {label}: {seconds // 60}m {seconds % 60:02d}s", flush=True)


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
    name: str  # what you type, e.g. build_host
    file: Path  # config/<name>.yaml

    @property
    def output_image(self):
        return OUTPUT_DIR / f"{self.name}.img"


def discover_configs():
    return [Config(path.stem, path) for path in sorted(CONFIG_DIR.glob("*.yaml"))]


def find_config(name):
    name = name.removesuffix(".yaml")
    configs = discover_configs()
    for config in configs:
        if config.name == name:
            return config
    available = ", ".join(c.name for c in configs) or "none"
    raise ScriptError(f"no config called '{name}' (available: {available})")


# --- rpi-image-gen ------------------------------------------------------------


def check_rpi_image_gen():
    """Make sure rpi-image-gen is there; if the submodule is not fetched, offer to fetch it."""
    if RPI_IMAGE_GEN.is_file():
        return
    if not USING_SUBMODULE:
        raise ScriptError(f"RPI_IMAGE_GEN points at {RPI_IMAGE_GEN}, which does not exist")

    fetch = ["git", "-C", ROOT, "submodule", "update", "--init", "--", "rpi-image-gen"]
    print("rpi-image-gen (a git submodule of this repository) has not been fetched yet.")
    if not sys.stdin.isatty():
        raise ScriptError(f"fetch it with: {shlex.join(str(part) for part in fetch)}")
    answer = input("Fetch it now? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        raise ScriptError("cancelled; rpi-image-gen is needed to build")
    run(fetch)
    if not dry_run and not RPI_IMAGE_GEN.is_file():
        raise ScriptError(f"still no {RPI_IMAGE_GEN} after fetching the submodule")


def rig_args(config):
    """The options every rpi-image-gen command needs to find this config."""
    return ["-S", SOURCE_DIR, "-c", config.file.name, "-B", BUILD_DIR]


def config_value(config, key):
    """A setting as the config resolves it (includes and overrides applied); "" if unset."""
    rig_dir = RPI_IMAGE_GEN.parent
    output = capture(
        [rig_dir / "bin" / "ig", "config", "-S", SOURCE_DIR, config.file],
        cwd=rig_dir,  # ig looks for its built-in configs relative to here
    )
    for line in output.splitlines():
        if line.startswith(f"CFG IGconf_{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def image_name(config):
    name = config_value(config, "image_name")
    if not name:
        raise ScriptError(f"could not work out the image name for '{config.name}'")
    return name


def bootenv_files(config):
    """The config's bootenv: files:, read from the file itself rather than through ig,
    whose Python modules are Debian only, so that flashing works on any Linux host."""
    try:
        import yaml
    except ImportError:
        raise ScriptError("reading the config needs PyYAML (python3-pyyaml on Fedora, "
                          "python3-yaml on Debian), or pass --no-env") from None
    settings = yaml.safe_load(config.file.read_text()) or {}
    return str((settings.get("bootenv") or {}).get("files") or "").split()


def env_files(config):
    """The environment/ files the config wants on the card (bootenv: files:)."""
    names = bootenv_files(config)
    missing = [name for name in names if not (ENV_DIR / name).is_file()]
    if missing:
        raise ScriptError(
            f"'{config.name}' needs {', '.join(missing)} in {ENV_DIR.relative_to(ROOT)}/ "
            "(see the .example files there), or pass --no-env to flash without them"
        )
    return [ENV_DIR / name for name in names]


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
    started_at = time.time()
    if not dry_run:
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
    with timed("rpi-image-gen build"):
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


def boot_partition(disk_path):
    """The FAT partition on a freshly flashed disk."""
    output = capture(["lsblk", "--json", "--output", "PATH,TYPE,FSTYPE", disk_path])
    for part in json.loads(output)["blockdevices"]:  # a flat list: the disk, then its partitions
        if part.get("type") == "part" and part.get("fstype") == "vfat":
            return part["path"]
    raise ScriptError(f"no boot (vfat) partition found on {disk_path} after flashing")


def copy_env(disk_path, files):
    """Put the secrets on the card's boot partition, for the bootenv layer to install."""
    # The kernel still has the partitions from before the image was written
    run(["sudo", "blockdev", "--rereadpt", disk_path])
    run(["sudo", "udevadm", "settle"])
    part = "<boot partition>" if dry_run else boot_partition(disk_path)
    unmount_partitions(disk_path)  # in case the desktop has just mounted it
    with tempfile.TemporaryDirectory(prefix="pi-boot-") as mountpoint:
        run(["sudo", "mount", part, mountpoint])
        try:
            target = f"{mountpoint}/{BOOT_ENV_DIR}"
            run(["sudo", "install", "-d", target])
            run(["sudo", "install", "-m", "0600", *files, target])
        finally:
            run(["sudo", "umount", mountpoint])
    print(f"copied {', '.join(f.name for f in files)} to {BOOT_ENV_DIR}/ on the boot partition")


def image_size(image):
    """The size of the disk image, uncompressed."""
    if image.suffix != ".xz":
        return image.stat().st_size
    for line in capture(["xz", "--robot", "--list", image]).splitlines():
        fields = line.split("\t")
        if fields[0] == "file":
            return int(fields[4])
    raise ScriptError(f"could not read the uncompressed size of {image}")


def write_image(image, disk_path):
    dd = ["sudo", "dd", f"of={disk_path}", "bs=4M", "conv=fsync", "status=progress"]
    if image.suffix != ".xz":
        run([*dd[:2], f"if={image}", *dd[2:]])
        return
    dd.append("iflag=fullblock")  # reads from a pipe can come back short
    print(f"$ xz -dc {shlex.quote(str(image))} | {shlex.join(dd)}", flush=True)
    if dry_run:
        return
    subprocess.run(["sudo", "-v"], check=True)  # ask for the password before the pipe starts
    xz = subprocess.Popen(["xz", "-dc", str(image)], stdout=subprocess.PIPE)
    try:
        subprocess.run(dd, stdin=xz.stdout, check=True)
    finally:
        xz.stdout.close()
        if xz.wait() != 0:
            raise ScriptError(f"xz could not decompress {image}; the card is not usable")


def flash(image, disk_path, allow_fixed, env=()):
    """Write the image (.img or .img.xz) to the disk, then the env files onto its boot
    partition. Checks the disk again, as a long build can change things."""
    if not dry_run and not image.is_file():
        raise ScriptError(f"{image} not found - build it first")
    size = image_size(image) if image.is_file() else 0
    disk = check_target(disk_path, size, allow_fixed)
    print(f"Flashing {image.name} to {disk.describe()}", flush=True)
    unmount_partitions(disk.path)
    with timed("flash"):
        write_image(image, disk.path)
        run(["sync"])
    if env:
        copy_env(disk.path, env)
    print(f"done - safe to remove {disk.path}")


# --- commands -----------------------------------------------------------------


def cmd_list(args):
    configs = discover_configs()
    if not configs:
        print(f"no configs found in {CONFIG_DIR}")
    for config in configs:
        print(f"{config.name:<20} {config.file.relative_to(ROOT)}")


def cmd_build(args):
    config = find_config(args.config)
    check_rpi_image_gen()  # before asking about a disk or starting a long build
    target = None
    env = ()
    if args.flash is not None:
        env = () if args.no_env else env_files(config)  # missing files fail now, not after the build
        target = select_target(args.flash, args.allow_fixed)  # choose now, not after the build
    image = build(config)
    if target:
        flash(image, target, args.allow_fixed, env)


def cmd_flash(args):
    config = find_config(args.config)
    env = ()
    if not args.no_env:
        env = env_files(config)
    target = select_target(args.device or "", args.allow_fixed)
    flash(config.output_image, target, args.allow_fixed, env)


def unpack_artifact(zip_path, into):
    """A CI run's artifact download: a .zip holding <config>.img.xz and its .sha256."""
    with zipfile.ZipFile(zip_path) as archive:
        images = [n for n in archive.namelist() if n.endswith((".img", ".img.xz"))]
        if len(images) != 1:
            raise ScriptError(f"{zip_path.name} should hold one .img or .img.xz, not {len(images)}")
        print(f"unpacking {zip_path.name}", flush=True)
        archive.extractall(into)
    return Path(into) / images[0]


def verify_checksum(image):
    sums = image.with_name(image.name + ".sha256")
    if not sums.is_file():
        print(f"(no {sums.name} next to it, so its checksum is not checked)")
        return
    print(f"checking {image.name} against {sums.name}", flush=True)
    capture(["sha256sum", "--check", "--strict", sums.name], cwd=image.parent)


def config_for_image(image, name):
    """The config whose environment/ files go on the card: --config, or the file name."""
    guess = image.name.removesuffix(".xz").removesuffix(".img")
    try:
        return find_config(name or guess)
    except ScriptError as err:
        if name:
            raise
        raise ScriptError(f"{err}; name the config with --config, or pass --no-env") from None


def cmd_flash_image(args):
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise ScriptError(f"{image} not found")
    # Unpacked next to the download, not in /tmp, which may be RAM
    with tempfile.TemporaryDirectory(prefix=".flash-image-", dir=image.parent) as unpacked:
        if image.suffix == ".zip":
            image = unpack_artifact(image, unpacked)
        elif not image.name.endswith((".img", ".img.xz")):
            raise ScriptError(f"{image.name} is not a .img, .img.xz or .zip")
        verify_checksum(image)
        env = ()
        if not args.no_env:
            config = config_for_image(image, args.config)
            env = env_files(config)
        target = select_target(args.device or "", args.allow_fixed)
        flash(image, target, args.allow_fixed, env)


def cmd_clean(args):
    config = find_config(args.config)
    check_rpi_image_gen()
    clean(config)


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
    building.add_argument("config", help="config name, e.g. build_host")
    building.add_argument("--flash", nargs="?", const="", type=device_path, metavar="DEVICE",
                          help="flash afterwards; without DEVICE, pick from a list")
    building.add_argument("--allow-fixed", action="store_true",
                          help="allow flashing a disk that does not look removable")
    building.add_argument("--no-env", action="store_true",
                          help="don't copy the config's environment/ files onto the card")
    building.set_defaults(func=cmd_build)

    flashing = commands.add_parser("flash", help="flash an image that is already built")
    flashing.add_argument("config", help="config name, e.g. build_host")
    flashing.add_argument("device", nargs="?", type=device_path,
                          help="target disk; omit to pick from a list")
    flashing.add_argument("--allow-fixed", action="store_true",
                          help="allow flashing a disk that does not look removable")
    flashing.add_argument("--no-env", action="store_true",
                          help="don't copy the config's environment/ files onto the card")
    flashing.set_defaults(func=cmd_flash)

    flashing_image = commands.add_parser(
        "flash-image", help="flash a pre-built image (.img, .img.xz, or a CI artifact .zip)")
    flashing_image.add_argument("image", help="the image file, eg ~/Downloads/build_host.zip")
    flashing_image.add_argument("device", nargs="?", type=device_path,
                                help="target disk; omit to pick from a list")
    flashing_image.add_argument("--config", metavar="NAME",
                                help="config whose environment/ files go on the card "
                                     "(default: from the image's file name)")
    flashing_image.add_argument("--allow-fixed", action="store_true",
                                help="allow flashing a disk that does not look removable")
    flashing_image.add_argument("--no-env", action="store_true",
                                help="don't copy the config's environment/ files onto the card")
    flashing_image.set_defaults(func=cmd_flash_image)

    cleaning = commands.add_parser("clean", help="remove the build tree for a config")
    cleaning.add_argument("config", help="config name, e.g. build_host")
    cleaning.set_defaults(func=cmd_clean)

    return parser.parse_args(argv)


def main(argv=None):
    global dry_run
    args = parse_args(argv)
    dry_run = args.dry_run
    try:
        with timed("total"):
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
