# git-runner layer

A self-hosted GitHub Actions runner for one repository. On first boot it downloads the runner, checks its hash, and registers it with the repo. After that it keeps `run.sh` running. Shared: any config can use it.

## Using it

Put the token in a file under `environment/` (git-ignored). Then add the layer to a config and set its variables in a `runner:` section:

```yaml
layer:
  runner: git-runner

runner:
  repo: https://github.com/owner/repo
  token_file: ${@SRCROOT}/environment/git-runner.token
```

See `config/build_host.yaml` for a working example.

## Variables

| Variable     | Default     | Meaning |
|--------------|-------------|---------|
| `repo`       | *(required)* | The repository URL, `https://github.com/owner/repo`. Passed to `config.sh --url`. |
| `token_file` | *(required)* | A file on the build host, as an absolute path, no spaces. It holds either a registration token or a personal access token (see Notes). It is copied into the image, readable only by the runner user. The build fails if the file doesn't exist. |
| `user`       | `runner`    | The account the runner runs as, so workflow jobs run as this account too. It is created if it doesn't exist. The runner goes in `~/actions-runner/`. |
| `name`       | *(hostname)* | The name the runner registers under. An existing runner with the same name is replaced. |
| `labels`     | *(empty)*   | Extra labels, comma separated, added to the defaults (`self-hosted`, `Linux`, `ARM64`). |
| `version`    | `2.337.0`   | The [actions/runner](https://github.com/actions/runner/releases) release to download. |
| `sha256`     | *(the hash for 2.337.0)* | The SHA-256 of `actions-runner-linux-arm64-<version>.tar.gz`. If you change `version`, change this too. |
| `assetdir`   | `${DOTD}`   | Where the layer reads its own files from (`git-runner.d/`). Don't change it. |

## What it installs

- Packages: `curl`, `ca-certificates` and `git`, plus the runtime libraries the runner needs (`libicu76`, `libkrb5-3`, `liblttng-ust1t64`, `libssl3t64`, `zlib1g`). This means `bin/installdependencies.sh` never has to run on the device.
- `~/runner.token`: the `token_file`, with mode 0600. Setup deletes it once the runner is registered.
- `/usr/local/bin/git-runner-setup`: does what GitHub's "New self-hosted runner" page describes: create `~/actions-runner`, download the tarball, check its hash, extract it, and run `config.sh --unattended --replace --url ... --token ...`. Then it deletes `~/runner.token`, since workflow jobs run as the same user and could otherwise read it. If the runner is already registered (`~/actions-runner/.runner` exists), it only makes sure the token is gone.
- `git-runner-setup.service`: a oneshot unit that runs the script as the runner user after the network and the clock are ready. If the script fails, the unit retries every minute.
- `git-runner.service`: runs `~/actions-runner/run.sh` as the runner user, after setup has succeeded, and restarts it whenever it exits. The runner exits after it updates itself.

## Notes

- **Token.** A registration token from the repo's *Settings → Actions → Runners → New self-hosted runner* page expires one hour after it is created. That is usually too short for a build, a flash and a first boot. Instead, use a fine-grained personal access token (`github_pat_...` or `ghp_...`) with *Administration: Read and write* on the repo. The setup script recognises a token by its prefix and exchanges it for a fresh registration token. Anything else is passed straight to `config.sh`.
- Registration only happens once. To register again, for example after removing the runner on GitHub, run `rm ~/actions-runner/.runner` on the device, put a token in `~/runner.token` again (mode 0600), and restart `git-runner-setup.service`.
- The runner is downloaded on first boot, not baked into the image. The device needs internet access the first time it starts.
- Docker is not included. If your workflows use container jobs or `docker` steps, add the `docker-debian-trixie` layer and add the runner user to the `docker` group.
