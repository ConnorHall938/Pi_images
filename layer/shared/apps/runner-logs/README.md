# runner-logs layer

Gives a kiosk page on the runner's device the logs of the jobs it runs. Used with the `git-runner` layer (it requires it), for `resources/runner-kiosk.html`.

A kiosk page can get runners, runs, jobs and steps from GitHub's REST API itself, but not the logs:

- GitHub's REST API only serves a job's log once the job has finished. While a job runs, its output is only on the device: the runner writes each step's output to `~/actions-runner/_diag/pages/*.log`, uploads it, and deletes it.
- The kiosk browser runs as another user and can't read those files.
- A finished job's log comes back from GitHub as a redirect to a signed storage link. The service follows it without the token, since the storage behind it rejects one.

So this layer runs a small Python service, as the runner user, on `127.0.0.1` only.

## Using it

```yaml
layer:
  runner: git-runner
  runnerlogs: runner-logs
```

## Variables

| Variable   | Default   | Meaning |
|------------|-----------|---------|
| `port`     | `8765`    | Port on `127.0.0.1`. `LOG_SERVER` in the kiosk page must match. |
| `assetdir` | `${DOTD}` | Where the layer reads its own files from (`runner-logs.d/`). Don't change it. |

The runner user and directory come from the `git-runner` layer's `runner.user`.

## What it installs

- The `python3` package.
- `/usr/local/bin/runner-logs`: the service, standard library only.
  - `GET /live?since=<unix time>` returns the newest page file written since `since` (the output of the step running now, last 256 KB) and the runner's name, as JSON.
  - `GET /job-log?repo=owner/repo&job=<id>` fetches a finished job's log from GitHub with the request's `Authorization` header and returns the last 2 MB as text.
  - Every response allows any origin, because the kiosk page is a `file://` page.
- `runner-logs.service`: runs it as the runner user, and restarts it if it exits.

## Notes

- Live output covers the current step only. The runner deletes a step's page file once it has uploaded it, so earlier steps' output comes from GitHub once the job has finished.
- The runner masks secrets before it writes the page files, so they show up as `***` here too.
- The service holds no token. `/job-log` uses whatever token the caller sends, and only for that one GitHub URL.
