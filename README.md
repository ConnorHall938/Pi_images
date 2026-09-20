# Pi_images

Raspberry Pi images, built with [rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen) (a git submodule).

```bash
git submodule update --init                  # once, after cloning
./build.py build tv_image                    # -> output/tv_image.img
./build.py build tv_image --flash            # then pick a disk from a list
./build.py build tv_image --flash /dev/sdb   # or name the disk
```

Other commands: `list`, `flash`, `clean`. Add `--dry-run` before the command to see what it would do.

Layout: `config/` has the configs, `layer/` the layers, `assets/` the files configs point at.
