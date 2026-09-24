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
