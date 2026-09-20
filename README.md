# Pi_images
Collection of Pi images

This repository is one [rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen)
source tree, laid out like rpi-image-gen itself. `build.py` builds a config by name;
rpi-image-gen is expected at `../rpi-image-gen` (or set `RPI_IMAGE_GEN` to its executable).

```
config/<name>.yaml      a buildable config
layer/shared/           layers reused by several images
layer/<image>/          layers (and their .d hooks/overlays) for one image
assets/<image>/         files a config points at: ${@SRCROOT}/assets/<image>/...
```

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

Every layer under `layer/` is loaded for every build, so a broken layer file fails
all of them. Layer names must be unique.
