[Unit]
Description=GitHub Actions runner
Requires=git-runner-setup.service
After=git-runner-setup.service network-online.target
Wants=network-online.target

[Service]
User=$RUNNER_USER
WorkingDirectory=$RUNNER_DIR
ExecStart=$RUNNER_DIR/run.sh
Restart=always
RestartSec=10
KillMode=process
KillSignal=SIGINT
TimeoutStopSec=5min

[Install]
WantedBy=multi-user.target
