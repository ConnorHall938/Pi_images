[Unit]
Description=Clone rpi-image-gen and install its dependencies
After=network-online.target
Wants=network-online.target
After=systemd-time-wait-sync.service
Requires=systemd-time-wait-sync.service
Before=git-runner.service

[Service]
Type=oneshot
RemainAfterExit=yes
Environment="BUILDER_URL=$BUILDER_URL"
Environment="BUILDER_BRANCH=$BUILDER_BRANCH"
Environment="DEBIAN_FRONTEND=noninteractive"
ExecStart=/usr/local/bin/rpi-builder-setup
Restart=on-failure
RestartSec=60
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
