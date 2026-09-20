# Build the tv_image Raspberry Pi image with rpi-image-gen.
#
#   make tv_image   build the image and copy it to ./output/tv_image.img
#                   (converts tv_image/splash.png to splash.tga first)
#   make cleanup    remove the build tree (./build)

RPI_IMAGE_GEN ?= ../rpi-image-gen/rpi-image-gen

SRC_DIR    := $(CURDIR)/tv_image
CONFIG     := tv_image.yaml
BUILD_DIR  := $(CURDIR)/build
OUTPUT_DIR := $(CURDIR)/output

# Must match `image: name:` in tv_image/config/tv_image.yaml
IMAGE_NAME := mytvimage

# Splash screen: keep the PNG, the TGA the layer needs is generated from it
SPLASH_PNG := $(SRC_DIR)/splash.png
SPLASH_TGA := $(SRC_DIR)/splash.tga
PNG2SPLASH := $(CURDIR)/tools/png2splash.py

# Target block device for `make flash`, e.g. DEVICE=/dev/sdb (no default on purpose)
DEVICE ?=
# Image that `make flash` writes
IMAGE  ?= $(OUTPUT_DIR)/tv_image.img

.PHONY: tv_image cleanup flash check-device build-flash

# Regenerated only when the PNG or the converter changes
$(SPLASH_TGA): $(SPLASH_PNG) $(PNG2SPLASH)
	python3 $(PNG2SPLASH) $(SPLASH_PNG) $(SPLASH_TGA)

$(SPLASH_PNG):
	@echo "error: $(SPLASH_PNG) not found - add your splash image (any PNG)" >&2; exit 1

tv_image: $(SPLASH_TGA)
	mkdir -p $(BUILD_DIR)
	$(RPI_IMAGE_GEN) build -S $(SRC_DIR) -c $(CONFIG) -B $(BUILD_DIR)
	mkdir -p $(OUTPUT_DIR)
	img=$$(find $(BUILD_DIR) -type f -name '$(IMAGE_NAME).img' | head -n 1); \
	if [ -z "$$img" ]; then \
		echo "error: $(IMAGE_NAME).img not found under $(BUILD_DIR)" >&2; exit 1; \
	fi; \
	cp -v "$$img" $(OUTPUT_DIR)/tv_image.img

cleanup:
	$(RPI_IMAGE_GEN) clean -S $(SRC_DIR) -c $(CONFIG) -B $(BUILD_DIR)

# Sanity-check DEVICE before anything destructive (or slow) happens.
check-device:
	@[ -n "$(DEVICE)" ] || { \
		echo "usage: make $(MAKECMDGOALS) DEVICE=/dev/sdX" >&2; \
		lsblk -o NAME,SIZE,TYPE,RM,TRAN,MODEL,MOUNTPOINTS >&2; exit 1; }
	@[ "$$(lsblk -dno TYPE $(DEVICE) 2>/dev/null)" = disk ] || { \
		echo "error: $(DEVICE) is not a whole disk (use /dev/sdX, not /dev/sdX1)" >&2; exit 1; }
	@if lsblk -nro MOUNTPOINT $(DEVICE) | grep -qxE '/|/boot|/boot/firmware'; then \
		echo "error: $(DEVICE) holds the running system (/ or /boot). Refusing." >&2; exit 1; fi

# Build the image, then write it to DEVICE:  make build-flash DEVICE=/dev/sdX
# DEVICE is checked first so a typo doesn't cost you a full build.
build-flash: check-device
	$(MAKE) tv_image
	$(MAKE) flash

# Write ./output/tv_image.img to a USB/SD card:  make flash DEVICE=/dev/sdX
# Destroys everything on DEVICE. Refuses a disk that holds / or /boot.
flash: check-device
	@[ -f $(IMAGE) ] || { \
		echo "error: $(IMAGE) not found (build it first)" >&2; exit 1; }
	@lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS $(DEVICE)
	-sudo umount $(DEVICE)?* 2>/dev/null
	sudo dd if=$(IMAGE) of=$(DEVICE) bs=4M conv=fsync status=progress
	sync
	@echo "done - safe to remove $(DEVICE)"
