# kiosk layer

Boots the image straight into a full-screen Chromium on Wayland ([cage](https://github.com/cage-kiosk/cage)), loading a URL or a local HTML file. Shared: any config can use it.

## Using it

In a config, add the layer and set any variables in a `kiosk:` section:

```yaml
layer:
  app: kiosk          # the key name is arbitrary; the value is the layer name

kiosk:
  page: ${@SRCROOT}/resources/runner-kiosk.html   # a local file, installed into the image
  #url: http://localhost:8123                     # or a web page (ignored if page is set)
  envfile: kiosk.env                              # secrets for the page, from the boot partition
  user: runner-kiosk
  rotation: 90
```

See `config/build_host.yaml` for a working example.

## Variables

All optional; the defaults are used for anything left out.

| Variable   | Default               | Meaning |
|------------|-----------------------|---------|
| `url`      | `https://example.com` | A web page to load, `http://` or `https://`, no spaces (e.g. `http://localhost:8123` for something running on the device). The kiosk waits for it to answer before opening the browser. Ignored when `page` is set. |
| `page`     | *(empty)*             | A file on the build host, as an absolute path (use `${@SRCROOT}/resources/...`), no spaces. It is copied into the image at `/usr/share/kiosk/<filename>` and loaded from there as `file://`. The build fails if the file doesn't exist. Keep these files in the repo's `resources/` folder. |
| `envfile`  | `kiosk.env`           | The name of an environment file (`KEY=value` lines) for tokens and anything else that shouldn't be in the image. It is not built in: put it in the card's boot partition, in an `environment/` folder (`./build.py flash` does this from the repo's `environment/` when the config lists it under `bootenv: files:`). The [bootenv](../../system/bootenv/README.md) layer installs it at boot as `/etc/kiosk/kiosk.env` (root and the kiosk user, mode 0640), and `kiosk.service` loads it. With `page`, every `${KEY}` in the page is replaced with its value when the kiosk starts. Empty for none. |
| `user`     | `kiosk-user`          | Account the kiosk runs as. Created at build time and added to the `video`, `render` and `input` groups. |
| `rotation` | `0`                   | `0`, `90`, `180` or `270`. Applied to the first display output with `wlr-randr --transform` before the browser starts. If the picture turns the wrong way, use `270` instead of `90` (or the reverse). |
| `touch_matrix` | *(empty)*         | Six space-separated numbers, libinput's calibration matrix for touchscreens. Empty means one matching `rotation` is used (none for `0`). Set it only if touches land in the wrong place. See Notes. |
| `assetdir` | `${DOTD}`             | Where the layer's own files are read from (`kiosk.d/`). Leave alone. |

## What it installs

- Packages: `cage`, `chromium`, `curl`, `gettext-base` (for `envsubst`), `wlr-randr`.
- `/usr/local/bin/kiosk-session`: generated at build time with the URL and rotation filled in. `cage` runs it; it rotates the display (if asked), waits for an `http(s)` page to answer, and then execs Chromium in `--kiosk` mode, with its profile in `/run/kiosk/chromium` (so nothing persists between boots).
- `/usr/share/kiosk/<filename>`: the `page` file, only when `page` is set.
- `/etc/bootenv.d/kiosk.conf`: the rule that sends `envfile` from the boot partition to `/etc/kiosk/kiosk.env`, when `envfile` is set.
- `/etc/udev/rules.d/99-kiosk-touch.rules`: when `rotation` is not `0` (or `touch_matrix` is set), sets `LIBINPUT_CALIBRATION_MATRIX` on every touchscreen, so touch follows the rotated picture.
- `/etc/systemd/system/kiosk.service`: rendered from `kiosk.d/kiosk.service.tpl` and enabled. Runs `cage` on `tty1` as the kiosk user, restarts it if it exits, and waits for `network-online` and time sync first.

Requires `device-user-admin`, `systemd-net-min`, `systemd-timesyncd` and `bootenv` (pulled in automatically).

## Layout

```
kiosk.yaml                        layer: metadata, variables, packages, build hooks
kiosk.d/
  kiosk.service.tpl               systemd unit template (filled in with envsubst)
```

`kiosk.d` must stay next to `kiosk.yaml` and keep the same name as the yaml (minus the extension), or the service template is not found.

## Notes

- The layer ships no page of its own; each config brings its own through `page`, so two images can show different content from the same layer. A page that loads other local files (images, CSS) needs them inline or hosted, since only that one file is copied.
- With an `envfile`, the page is filled in at start up, not at build time: `kiosk-session` runs `envsubst` on it, limited to the keys in `/etc/kiosk/kiosk.env`, and writes the result to `/run/kiosk/<filename>` (private to the kiosk user, in RAM), which Chromium loads. So the file in `/usr/share/kiosk/` keeps its `${KEY}` placeholders, and other `${...}` in the page (eg JavaScript template literals) are left alone. To change a value, edit `/etc/kiosk/kiosk.env` on the device and restart `kiosk.service`. The value is still visible to anyone who can view the page's source on the screen.
- For an `http(s)` `url`, the session polls it (2s apart, up to 10 minutes) and then opens the browser whether or not it answered. This is so a page served by a container that is still starting (or still pulling its images on first boot) doesn't leave Chromium on an error page. A `page` file is not waited for.
- Chromium's profile is in `/run`, so it forgets everything on reboot, including any login. A page that needs one has to allow it without logging in (e.g. Home Assistant's `trusted_networks` for `127.0.0.1`, which needs no user ID when there is only one user).
- `wlr-randr --transform` rotates the picture but not touch input, which is why the udev rule exists. `--transform N` turns the picture counter-clockwise by N degrees, and the default matrices match that (`90` gives `0 -1 1 1 0 0`, `270` gives `0 1 0 -1 0 1`, `180` gives `-1 0 1 0 -1 1`), confirmed on a real screen. If touches still land in the wrong place, set `touch_matrix` explicitly. To try one without rebuilding, edit `/etc/udev/rules.d/99-kiosk-touch.rules` on the device and run `sudo udevadm trigger --subsystem-match=input --action=change`, then restart `kiosk.service`. Whichever matrix works, put it in `touch_matrix` so it survives a reflash.
- The kiosk user is passwordless; there is no login prompt on the kiosk screen.
- Build with `./build.py build <config>` from the repo root. The repo root is passed to rpi-image-gen as `-S`, so this layer is found automatically.
