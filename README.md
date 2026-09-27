# Pi_images

Raspberry Pi images, built with [rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen) (a git submodule).

```bash
git submodule update --init                  # once, after cloning
./build.py build build_host                  # -> output/build_host.img
./build.py build build_host --flash          # then pick a disk from a list
./build.py build build_host --flash /dev/sdb # or name the disk
```

To flash an image built somewhere else, such as by CI, pass the file: a `.img`, a release's `.img.xz`, or the `.zip` from a run's Artifacts. It checks the `.sha256` if there is one, and copies the secrets for the config named by the file (or `--config NAME`):

```bash
./build.py flash-image ~/Downloads/build_host.zip           # pick a disk from a list
./build.py flash-image build_host.img.xz /dev/sdb --no-env  # without the secrets
```

Other commands: `list`, `flash`, `clean`. Add `--dry-run` before the command to see what it would do.

Layout: `config/` has the configs, `layer/` the layers, `resources/` the files configs put in the image (committed), `environment/` the local SSH key, Wi-Fi profiles and secrets (git-ignored apart from `ssh.pub` and the examples).

Secrets are not built into the images. Each config lists the `environment/` files its device needs under `bootenv: files:`. After writing the image, `flash` copies them into an `environment/` folder on the card's boot partition. On first boot the [bootenv](layer/shared/system/bootenv/README.md) layer moves them into place and shreds them from the card. To set up a card by hand instead, make that folder on the boot partition and copy the files in. Start from the `.example` files in `environment/`:

| Config                | Files |
|-----------------------|-------|
| `build_host`          | `VM8428755.psk`, `git-runner.token`, `kiosk.env` |
| `home_assistant_host` | `VM8428755.psk`, `ha.env` |

CI: `.github/workflows/build-images.yml` builds on the self-hosted runner (the `build_host` image). It runs by hand only: Actions → Build images → Run workflow, then pick the image and, optionally, a release tag. The compressed `<config>.img.xz` is attached to the run as an artifact, and to a release if you gave a tag. It needs no secrets: the images hold none, so put the files on the card after writing a downloaded image.
