# ha_config

Everything the Home Assistant host image (`config/home_assistant_host.yaml`) puts in `~/app/` on the device, through the `docker` layer.

```
compose.yaml                   the stack: Home Assistant, Mosquitto, Zigbee2MQTT, Frigate
files/                         copied into ~/app/ (the `files:` variable)
  config/                      Home Assistant's /config
    configuration.yaml
    .storage/core.config_entries   integrations that exist from first start: MQTT and Frigate
    custom_components/frigate      link to the submodule below
  frigate/config.yml
  mosquitto/mosquitto.conf
  zigbee2mqtt/configuration.yaml
frigate-hass-integration/      git submodule, pinned to a release tag
```

## Integrations set up at build time

`files/config/.storage/core.config_entries` is Home Assistant's own store of configured integrations. It has two entries, so they are already there on first boot and nothing is added in the UI:

- **MQTT**: broker `localhost:1883`. Mosquitto only publishes that port on `127.0.0.1`, which Home Assistant reaches because it runs on the host network.
- **Frigate**: `http://localhost:5000`, Frigate's unauthenticated API, published on `127.0.0.1` too.

This is only the starting state. Once Home Assistant is running it owns that file and rewrites it (adding whatever you set up in the UI), and the copy on the device is not put back into this repo. Reflashing resets it. If you give Mosquitto a password, don't commit it in this file.

## Frigate integration

Frigate is not built into Home Assistant, so its integration is a custom component. It comes from the `frigate-hass-integration` submodule, pinned to a tag, and `files/config/custom_components/frigate` is a symlink to the `custom_components/frigate` folder inside it. The docker layer copies symlinks as what they point to, so the image gets a real folder.

After cloning: `git submodule update --init`. Without it the link is broken and the build fails.

To move to another release:

```bash
git -C resources/ha_config/frigate-hass-integration fetch --tags
git -C resources/ha_config/frigate-hass-integration checkout v5.x.y
git add resources/ha_config/frigate-hass-integration
```

Each release needs a minimum Home Assistant version (`hacs.json` in the submodule; v5.15.6 needs 2026.3.0). The compose file uses the `stable` Home Assistant image, so pin that to a version once things work. The integration also installs two Python packages the first time it loads, so the device needs internet on first boot.
