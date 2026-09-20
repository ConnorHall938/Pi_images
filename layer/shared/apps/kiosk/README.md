# kiosk layer

Boots the image straight into a full-screen Chromium on Wayland ([cage](https://github.com/cage-kiosk/cage)), loading a URL or a local HTML file. Shared: any config can use it.

## Using it

In a config, add the layer and set any variables in a `kiosk:` section:

```yaml
layer:
  app: kiosk          # the key name is arbitrary; the value is the layer name

kiosk:
  page: ${@SRCROOT}/resources/tv_menu.html   # a local file, installed into the image
  #url: http://localhost:8123                # or a web page (ignored if page is set)
  user: tv-kiosk
  rotation: 90
```

See `config/tv_image.yaml` for a working example.

## Variables

All optional; the defaults are used for anything left out.

| Variable   | Default               | Meaning |
|------------|-----------------------|---------|
| `url`      | `https://example.com` | A web page to load, `http://` or `https://`, no spaces (e.g. `http://localhost:8123` for something running on the device). The kiosk waits for it to answer before opening the browser. Ignored when `page` is set. |
| `page`     | *(empty)*             | A file on the build host, as an absolute path (use `${@SRCROOT}/resources/...`), no spaces. It is copied into the image at `/usr/share/kiosk/<filename>` and loaded from there as `file://`. The build fails if the file doesn't exist. Keep these files in the repo's `resources/` folder. |
| `user`     | `kiosk-user`          | Account the kiosk runs as. Created at build time and added to the `video`, `render` and `input` groups. |
| `rotation` | `0`                   | `0`, `90`, `180` or `270`. Applied to the first display output with `wlr-randr --transform` before the browser starts. If the picture turns the wrong way, use `270` instead of `90` (or the reverse). |
| `assetdir` | `${DOTD}`             | Where the layer's own files are read from (`kiosk.d/`). Leave alone. |

## What it installs

- Packages: `cage`, `chromium`, `curl`, `wlr-randr`.
- `/usr/local/bin/kiosk-session`: generated at build time with the URL and rotation filled in. `cage` runs it; it rotates the display (if asked), waits for an `http(s)` page to answer, and then execs Chromium in `--kiosk` mode, with its profile in `/run/kiosk/chromium` (so nothing persists between boots).
- `/usr/share/kiosk/<filename>`: the `page` file, only when `page` is set.
- `/etc/systemd/system/kiosk.service`: rendered from `kiosk.d/kiosk.service.tpl` and enabled. Runs `cage` on `tty1` as the kiosk user, restarts it if it exits, and waits for `network-online` and time sync first.

Requires `device-user-admin`, `systemd-net-min` and `systemd-timesyncd` (pulled in automatically).

## Layout

```
kiosk.yaml                        layer: metadata, variables, packages, build hooks
kiosk.d/
  kiosk.service.tpl               systemd unit template (filled in with envsubst)
```

`kiosk.d` must stay next to `kiosk.yaml` and keep the same name as the yaml (minus the extension), or the service template is not found.

## Notes

- The layer ships no page of its own; each config brings its own through `page`, so two images can show different content from the same layer. A page that loads other local files (images, CSS) needs them inline or hosted, since only that one file is copied.
- For an `http(s)` `url`, the session polls it (2s apart, up to 10 minutes) and then opens the browser whether or not it answered. This is so a page served by a container that is still starting (or still pulling its images on first boot) doesn't leave Chromium on an error page. A `page` file is not waited for.
- Chromium's profile is in `/run`, so it forgets everything on reboot, including any login. A page that needs one has to allow it without logging in (e.g. Home Assistant's `trusted_networks` for `127.0.0.1`).
- The kiosk user is passwordless; there is no login prompt on the kiosk screen.
- Build with `./build.py build <config>` from the repo root. The repo root is passed to rpi-image-gen as `-S`, so this layer is found automatically.
