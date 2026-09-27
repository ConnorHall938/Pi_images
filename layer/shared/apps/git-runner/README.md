# git-runner layer

A self-hosted GitHub Actions runner for one repository. On first boot it downloads the runner, checks its hash, and registers it with the repo. After that it keeps `run.sh` running. Shared: any config can use it.

## Using it

Add the layer to a config and set its variables in a `runner:` section:

```yaml
layer:
  runner: git-runner

runner:
  repo: https://github.com/owner/repo

bootenv:
  files: git-runner.token   # and the Wi-Fi profile etc
```

The token is not built into the image. Put it in `environment/git-runner.token` (git-ignored) and `./build.py flash` copies it onto the card's boot partition, because the config lists it under `bootenv: files:`. The [bootenv](../../system/bootenv/README.md) layer then installs it on first boot.

See `config/build_host.yaml` for a working example.

## Variables

| Variable     | Default     | Meaning |
|--------------|-------------|---------|
| `repo`       | *(required)* | The repository URL, `https://github.com/owner/repo`. Passed to `config.sh --url`. |
| `token_file` | `git-runner.token` | The name of the token file on the card's boot partition, in its `environment/` folder. It holds either a registration token or a personal access token (see Notes). It is installed at boot as `~/runner.token`, readable only by the runner user. |
| `user`       | `runner`    | The account the runner runs as, so workflow jobs run as this account too. It is created if it doesn't exist. The runner goes in `~/actions-runner/`. |
| `name`       | *(hostname)* | The name the runner registers under. An existing runner with the same name is replaced. |
| `labels`     | *(empty)*   | Extra labels, comma separated, added to the defaults (`self-hosted`, `Linux`, `ARM64`). |
| `version`    | `2.337.0`   | The [actions/runner](https://github.com/actions/runner/releases) release to download. |
| `sha256`     | *(the hash for 2.337.0)* | The SHA-256 of `actions-runner-linux-arm64-<version>.tar.gz`. If you change `version`, change this too. |
| `assetdir`   | `${DOTD}`   | Where the layer reads its own files from (`git-runner.d/`). Don't change it. |

## What it installs

- Packages: `curl`, `ca-certificates` and `git`, plus the runtime libraries the runner needs (`libicu76`, `libkrb5-3`, `liblttng-ust1t64`, `libssl3t64`, `zlib1g`). This means `bin/installdependencies.sh` never has to run on the device.
- `/etc/bootenv.d/git-runner.conf`: the rule that sends `token_file` from the boot partition to `~/runner.token` (mode 0600). Setup deletes that once the runner is registered.
- `/usr/local/bin/git-runner-setup`: does what GitHub's "New self-hosted runner" page describes: create `~/actions-runner`, download the tarball, check its hash, extract it, and run `config.sh --unattended --replace --url ... --token ...`. Then it deletes `~/runner.token`, since workflow jobs run as the same user and could otherwise read it. If the runner is already registered (`~/actions-runner/.runner` exists), it only makes sure the token is gone.
- `git-runner-setup.service`: a oneshot unit that runs the script as the runner user after the network and the clock are ready. If the script fails, for example because there is no token yet, the unit retries every minute.
- `git-runner.service`: runs `~/actions-runner/run.sh` as the runner user, after setup has succeeded, and restarts it whenever it exits. The runner exits after it updates itself.

## Notes

- **Token.** A registration token from the repo's *Settings → Actions → Runners → New self-hosted runner* page expires one hour after it is created. That is usually too short for a build, a flash and a first boot. Instead, use a fine-grained personal access token (`github_pat_...` or `ghp_...`) with *Administration: Read and write* on the repo. The setup script recognises a token by its prefix and exchanges it for a fresh registration token. Anything else is passed straight to `config.sh`.
- Registration only happens once. To register again, for example after removing the runner on GitHub, run `rm ~/actions-runner/.runner` on the device. Then put a token in `~/runner.token` again (mode 0600) and restart `git-runner-setup.service`, or put it on the boot partition and reboot.
- The runner is downloaded on first boot, not baked into the image. The device needs internet access the first time it starts.
- Docker is not included. If your workflows use container jobs or `docker` steps, add the `docker-debian-trixie` layer and add the runner user to the `docker` group.
