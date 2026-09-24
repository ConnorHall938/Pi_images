[Unit]
Description=Download and register the GitHub Actions runner
After=network-online.target
Wants=network-online.target
After=systemd-time-wait-sync.service
Requires=systemd-time-wait-sync.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$RUNNER_USER
Environment="RUNNER_DIR=$RUNNER_DIR"
Environment="RUNNER_TOKEN_FILE=$RUNNER_TOKEN_FILE"
Environment="RUNNER_REPO=$RUNNER_REPO"
Environment="RUNNER_NAME=$RUNNER_NAME"
Environment="RUNNER_LABELS=$RUNNER_LABELS"
Environment="RUNNER_VERSION=$RUNNER_VERSION"
Environment="RUNNER_SHA256=$RUNNER_SHA256"
ExecStart=/usr/local/bin/git-runner-setup
Restart=on-failure
RestartSec=60
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
