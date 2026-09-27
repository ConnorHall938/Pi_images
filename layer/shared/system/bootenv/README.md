# bootenv layer

Keeps secrets out of the image. Wi-Fi passwords, tokens and `.env` files go onto the card's boot partition after flashing, not into the build. Early on every boot, this layer moves each one from there to where it belongs, then shreds it from the card. An image can then be shared or published without giving anything away, and one image can serve several devices with different secrets.

Shared: the kiosk, git-runner and docker layers depend on it, so it is pulled in automatically.

## Using it

List the files from the repo's `environment/` folder that the config's devices need:

```yaml
bootenv:
  files: VM8428755.psk git-runner.token kiosk.env
```

`./build.py flash <config>` (or `build --flash`) then copies them into an `environment/` folder on the card's boot partition after writing the image. It stops before writing anything if one is missing. Pass `--no-env` to leave them off.

To do it by hand instead, for example on another computer, create an `environment/` folder on the card's boot partition (the FAT one that any computer can open, with `config.txt` in it) and copy the files in.

To change a secret later, put the new file there and reboot, or edit the installed copy over SSH.

## Where files go

Each file goes where the first rule that matches its name says. Rules are lines in `/etc/bootenv.d/*.conf` in the image, and the layers write their own:

| File on the card  | Installed as                     | Rule from |
|-------------------|----------------------------------|-----------|
| `*.psk`, `*.open`, `*.8021x` | `/var/lib/iwd/<name>` (root, 0600): an iwd Wi-Fi profile, named after the network | this layer |
| `kiosk.env`       | `/etc/kiosk/kiosk.env` (root:kiosk user, 0640) | kiosk (`envfile`) |
| `git-runner.token` | `~runner/runner.token` (runner user, 0600) | git-runner (`token_file`) |
| `docker.env`      | `~user/app/.env` (the user, 0600) | docker (`envfile`; `ha.env` in `home_assistant_host`) |

A rule is `PATTERN DEST OWNER[:GROUP] MODE`, where `PATTERN` is a shell pattern for the file's name and a `DEST` that ends in `/` is a directory:

```
kiosk.env  /etc/kiosk/kiosk.env  root:runner-kiosk  0640
```

A layer of your own adds one from a build hook: `printf '...\n' > "$1/etc/bootenv.d/<layer>.conf"`.

## Variables

| Variable | Default    | Meaning |
|----------|------------|---------|
| `files`  | *(empty)*  | Names of files in the repo's `environment/` folder, space separated, that `./build.py flash` copies onto the card. The image itself doesn't use this. |

## What it installs

- `/usr/local/sbin/bootenv-install`: moves the files. Windows line endings are removed on the way, so files edited on Windows still work. A file with no matching rule is left on the card and logged. So are dotfiles, which covers the `._name` copies macOS leaves behind.
- `/etc/systemd/system/bootenv.service`: runs the script on every boot while the card's `environment/` folder has anything in it. The script removes the folder once it is empty. It runs before `sysinit.target`, so before iwd and every app service, and none of them need to order themselves after it.
- `/etc/bootenv.d/iwd.conf`: the Wi-Fi rules.

## Notes

- The files are overwritten (`shred`) and then deleted, because a plain delete on FAT leaves the contents readable on the card. The files are still readable on the card until the device first boots, so treat a prepared card like the secrets on it.
- `journalctl -u bootenv` on the device shows what was installed and what was left on the card. Without its secret, a service carries on as best it can: no Wi-Fi, the runner's setup retrying every minute, the kiosk page with its `${KEY}`s unfilled, and compose with empty values.
