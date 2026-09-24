[Unit]
Description=Serve the GitHub Actions runner's job logs to the kiosk
After=network-online.target
Wants=network-online.target

[Service]
User=$RUNNER_USER
Environment="RUNNER_DIR=$RUNNER_DIR"
Environment="RUNNER_LOGS_PORT=$RUNNER_LOGS_PORT"
ExecStart=/usr/local/bin/runner-logs
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
