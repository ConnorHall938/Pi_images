# docker layer

Runs a Docker Compose stack at boot, as a dedicated user. Builds on rpi-image-gen's `docker-debian-trixie` layer (engine, CLI, compose plugin), which is pulled in automatically. Shared: any config can use it.

## Using it

```yaml
layer:
  containers: docker  # the key name is arbitrary; the value is the layer name

docker:
  user: appuser
  compose: ${@SRCROOT}/resources/homeassistant/compose.yaml
  files:   ${@SRCROOT}/resources/homeassistant/files
  envfile: homeassistant.env   # from the boot partition, not the build

bootenv:
  files: homeassistant.env
```

`compose` is required; `user`, `files` and `envfile` are optional. Keep the compose file and `files` in the repo's `resources/` folder. The env file goes in `environment/` (git-ignored), and `./build.py flash` copies it onto the card because it is listed under `bootenv: files:`.

## Variables

| Variable   | Default       | Meaning |
|------------|---------------|---------|
| `user`     | `docker-user` | Account the stack runs as. Created if it doesn't exist, and added to the `docker` group. Membership of that group is root-equivalent on the device. |
| `compose`  | **required**  | The compose file on the build host, as an absolute path, no spaces. Installed as `~/app/compose.yaml` for that user and started at boot. The build fails if it is unset or the file doesn't exist. |
| `files`    | *(empty)*     | A directory on the build host, as an absolute path, no spaces. Its contents are copied into `~/app/` next to `compose.yaml`, so relative bind mounts in the compose file (e.g. `./config:/config`) find them. Owned by the user. Symlinks are followed and copied as what they point to, so it can link to content elsewhere in the repo (e.g. a git submodule); a broken link fails the build. If set but not a directory, the build fails. |
| `envfile`  | `docker.env`  | The name of an environment file (`KEY=value` lines) for passwords and anything else that shouldn't be in the image. It is not built in: it goes on the card's boot partition, in an `environment/` folder, and the [bootenv](../../system/bootenv/README.md) layer installs it at boot as `~/app/.env` (mode 0600, owned by the user). `docker compose` reads it for `${KEY}` in the compose file. It replaces any `.env` from `files`. Empty for none. |
| `assetdir` | `${DOTD}`     | Where the layer's own files are read from (`docker.d/`). Leave alone. |

The engine layer shares the `docker:` section, so `trust_user1: y` (which adds the image's main user to the `docker` group) goes in the same place.

## What it installs

- The `user` account, in the `docker` group.
- `/home/<user>/app/compose.yaml`: the `compose` file, owned by the user.
- `/home/<user>/app/...`: the contents of `files`, if set, owned by the user. If it contains its own `compose.yaml`, the `compose` variable wins.
- `/etc/bootenv.d/docker.conf`: the rule that sends `envfile` from the boot partition to `/home/<user>/app/.env` (mode 0600), if `envfile` is set.
- `/etc/systemd/system/docker-app.service`: rendered from `docker.d/docker-app.service.tpl` and enabled. It runs `docker compose up -d` as the user in `~/app`, after `docker.service`, the network and time sync, and `docker compose down` on stop.

## Layout

```
docker.yaml                        layer: metadata, variables, build hooks
docker.d/
  docker-app.service.tpl           systemd unit template (filled in with envsubst)
```

`docker.d` must stay next to `docker.yaml` and keep the same name as the yaml (minus the extension), or the service template is not found.

## Notes

- Images are pulled on first boot, so the device needs network then. Nothing is baked into the image, and that keeps it small.
- Anything the compose file refers to (bind-mounted config, `.env` files, `build:` contexts) has to be inside `files`, or it isn't in the image. Mount it with a relative path (`./config:/config`), which resolves against `~/app/`.
- `files` is a starting state. The containers can write to those directories at runtime (Home Assistant keeps its database and `.storage/` in its config directory), and reflashing resets them.
- Don't commit secrets. Put them in the `envfile` and refer to them as `${KEY}` in the compose file, which can pass them on to a container as environment variables.
- Use `restart: unless-stopped` (or similar) in the compose file so containers come back after a crash. The unit starts the stack once at boot.
- The engine layer here is the Trixie one (`docker-debian-trixie`), matching `trixie-minbase`. For Bookworm, change `X-Env-Layer-Requires` in `docker.yaml` to `docker-debian-bookworm`.
