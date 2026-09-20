[Unit]
Description=Docker Compose stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
After=systemd-time-wait-sync.service
Requires=systemd-time-wait-sync.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$DOCKER_USER
WorkingDirectory=$DOCKER_APPDIR
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
