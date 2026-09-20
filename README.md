# Pi_images
Collection of Pi images

Each image is a project under `configs/<project>/`, with its config at
`configs/<project>/config/<name>.yaml`. `build.py` builds one by name using
[rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen), expected at
`../rpi-image-gen` (or set `RPI_IMAGE_GEN` to its executable).

```bash
./build.py list                              # available configs
./build.py build tv_image                    # -> output/tv_image.img
./build.py build tv_image --flash            # then pick a disk from a numbered list
./build.py build tv_image --flash /dev/sdb   # then flash that disk
./build.py flash tv_image [/dev/sdb]         # flash an image that is already built
./build.py clean tv_image                    # remove the build tree
```

Put `--flash` last. Add `--dry-run` before the command to print what would run
without doing it. Flashing refuses the disk the machine is running from, and
anything that does not look removable unless `--allow-fixed` is given.
