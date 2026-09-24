# Pi_images

Raspberry Pi images, built with [rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen) (a git submodule).

```bash
git submodule update --init                  # once, after cloning
./build.py build build_host                  # -> output/build_host.img
./build.py build build_host --flash          # then pick a disk from a list
./build.py build build_host --flash /dev/sdb # or name the disk
```

Other commands: `list`, `flash`, `clean`. Add `--dry-run` before the command to see what it would do.

Layout: `config/` has the configs, `layer/` the layers, `resources/` the files configs put in the image (committed), `environment/` the local keys and Wi-Fi profiles configs point at (git-ignored).

CI: `.github/workflows/build-images.yml` builds on the self-hosted runner (the `build_host` image). It runs by hand only: Actions → Build images → Run workflow, then pick the image and, optionally, a release tag. The compressed `<config>.img.xz` is attached to the run as an artifact, and to a release if you gave a tag. It needs the repository secrets `WIFI_PSK`, `RUNNER_TOKEN`, `KIOSK_ENV` and `HA_ENV`, which hold the contents of the git-ignored `environment/` files.
