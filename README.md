# NetBox-EVE-NG Automation Framework

[![CI](https://github.com/E-Conners-Lab/netbox-eveng-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/E-Conners-Lab/netbox-eveng-automation/actions/workflows/ci.yml)

A Python automation framework that uses **NetBox as the source of truth** to provision and configure network labs in **EVE-NG**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         WORKFLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. DEFINE         2. POPULATE        3. PROVISION             │
│   ┌──────────┐      ┌──────────┐       ┌──────────┐            │
│   │ topology │ ───▶ │  NetBox  │ ───▶  │  EVE-NG  │            │
│   │   .yml   │      │  (SoT)   │       │   Lab    │            │
│   └──────────┘      └──────────┘       └──────────┘            │
│                          │                   │                  │
│   4. GENERATE       ◀────┘                   │                  │
│   ┌──────────┐                               │                  │
│   │  Device  │                               │                  │
│   │ Configs  │ ─────────────────────────────▶│                  │
│   └──────────┘      5. PUSH CONFIGS          │                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Declarative topology**: define your network in YAML
- **NetBox integration**: automatic population of devices, interfaces, IPs, and cables
- **EVE-NG provisioning**: creates labs, nodes, and connections via API
- **Multi-vendor**: Cisco IOS, Juniper Junos, and Arista EOS — vendor is resolved from NetBox and used to pick the right Jinja template and Netmiko driver
- **Config deployment**: pushes configs via SSH (Netmiko) or NETCONF (ncclient)

## Prerequisites

### On your workstation
- Docker + Docker Compose **— and the Docker daemon must be running before you start.** On macOS/Windows that means Docker Desktop is open; on Linux make sure the `docker` service is up. Verify with `docker info` — it should print system info, not an error.
- Python 3.10+

### On your EVE-NG host
- A reachable EVE-NG instance (community or pro), API enabled.
- A `pnet0` cloud bridge wired to whichever LAN your devices' management IPs live on (default behaviour for community ISO; verify with `cat /etc/network/interfaces`).
- The QEMU image referenced by your `device_types` already installed under `/opt/unetlab/addons/qemu/`, then run `/opt/unetlab/wrappers/unl_wrapper -a fixpermissions`. The shipped `topology.yml` uses Cisco vIOS (`vios-adventerprisek9-m.vmdk.SPA.157-3.M3`) — Cisco IOS images are licensed and not redistributed with this project.
- An empty lab created in the EVE-NG UI whose name matches `lab.name` in `topology.yml` (default: `Automation lab`). The orchestrator opens an existing lab; it does not create one.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/<you>/netbox-eveng-automation.git
cd netbox-eveng-automation
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create your `.env`

```bash
cp .env.example .env
```

Generate a real Django secret and a real NetBox API token:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))"
python -c "import secrets; print('SUPERUSER_API_TOKEN=' + secrets.token_hex(20))"
```

Paste both into `.env`. Then **set `NETBOX_TOKEN` to the same value as `SUPERUSER_API_TOKEN`** — NetBox provisions the superuser's first API token from `SUPERUSER_API_TOKEN`, and the orchestrator authenticates with `NETBOX_TOKEN`. They must match (or you can generate a separate token in the NetBox UI later and use that).

Fill in the rest: passwords, `EVENG_HOST/USER/PASS`, `ALLOWED_HOSTS` if accessing NetBox from anywhere besides `localhost`.

### 3. Start NetBox

```bash
docker compose up -d
docker compose logs -f netbox      # Ctrl+C once you see "Listening at: http://0.0.0.0:8080"
```

The first boot runs migrations and creates the superuser — usually 2-3 minutes. Visit `http://localhost:8000` and log in with `SUPERUSER_NAME` / `SUPERUSER_PASSWORD` from your `.env`.

### 4. Define your topology

Edit `topology.yml`. The shipped example uses RFC 5737 documentation IPs (`192.0.2.0/24`); change `management_network.gateway`, the per-device management IPs, and `ntp_server` to match your real lab network. Make sure `lab.name` matches the empty lab you created in EVE-NG.

### 5. Run the orchestrator

The shortcut — install deps, start the stack, prompt for confirmation, run the full pipeline:

```bash
./start.sh
```

Or run the orchestrator directly:

```bash
python orchestrator.py --full --insecure
```

Or step by step:

```bash
python orchestrator.py --populate-netbox     # Step 1: NetBox
python orchestrator.py --provision-eveng     # Step 2: EVE-NG
python orchestrator.py --configure-devices   # Step 3: device configs
python orchestrator.py --show-topology       # Just print the topology
```

The `--insecure` flag disables TLS verification — needed for EVE-NG self-signed certs. Drop it if your lab has real certs.

## Configuration

All connection details are read from environment variables (or a `.env` file via `python-dotenv`). CLI flags override env vars.

| Variable | Purpose |
|---|---|
| `NETBOX_URL` | NetBox base URL |
| `NETBOX_TOKEN` | NetBox API token |
| `EVENG_HOST` | EVE-NG host or IP |
| `EVENG_USER` | EVE-NG username |
| `EVENG_PASS` | EVE-NG password |
| `SECRET_KEY` | Django secret for the NetBox container |
| `POSTGRES_PASSWORD` | Postgres password for the NetBox container |
| `SUPERUSER_*` | NetBox initial superuser bootstrap |

See `.env.example` for the complete list.

## File layout

```
netbox-eveng-automation/
├── docker-compose.yml      # NetBox stack (Postgres + Redis + workers)
├── .env.example            # Template — copy to .env
├── requirements.txt        # Pinned Python dependencies
├── topology.yml            # Your network definition
├── orchestrator.py         # CLI entry point
├── scripts/
│   ├── netbox_client.py    # NetBox API wrapper
│   ├── eveng_client.py     # EVE-NG API wrapper
│   ├── config_generator.py # Jinja2 config rendering
│   └── device_configurator.py  # Push configs over SSH/NETCONF
├── templates/              # Optional override Jinja2 templates
└── configs/                # Generated configs (gitignored)
```

## Topology YAML reference

### Device

```yaml
devices:
  - name: "R1-CISCO"
    role: "router"
    device_type: "vios"
    site: "automation-lab"
    position:
      left: 20
      top: 30
    interfaces:
      - name: "GigabitEthernet0/0"
        description: "Management"
        ip_address: "192.0.2.101/24"
        enabled: true
        mgmt: true
```

### Cable

```yaml
cables:
  - a_device: "R1-CISCO"
    a_interface: "GigabitEthernet0/1"
    b_device: "R2-CISCO"
    b_interface: "GigabitEthernet0/1"
    description: "Point-to-point link"
```

### Device defaults

```yaml
device_defaults:
  domain: "automation.lab"
  username: "admin"
  password: "automation123"   # lab only — override before touching real gear
  enable_secret: "automation123"
  ssh_enabled: true
  netconf_enabled: true
  ntp_server: "192.0.2.1"
```

## Adding multi-vendor support

### Juniper

1. Add vSRX or vQFX to EVE-NG: `/opt/unetlab/addons/qemu/vsrx-XX.X/`
2. `/opt/unetlab/wrappers/unl_wrapper -a fixpermissions`
3. Extend `topology.yml`:

```yaml
device_types:
  - manufacturer: "juniper"
    model: "vSRX"
    slug: "vsrx"
    eveng_template: "vsrx"
    interfaces:
      - name: "ge-0/0/0"
        type: "1000base-t"
```

### Arista

1. Add vEOS to EVE-NG: `/opt/unetlab/addons/qemu/veos-X.X.X/`
2. Extend `topology.yml`:

```yaml
device_types:
  - manufacturer: "arista"
    model: "vEOS"
    slug: "veos"
    eveng_template: "veos"
```

## Custom Jinja2 templates

Drop a vendor-named template in `templates/`:

```jinja
{# templates/cisco.j2 #}
hostname {{ device.name }}
!
{% for interface in interfaces %}
interface {{ interface.name }}
 description {{ interface.description }}
 ip address {{ interface.ip_address | ip_address }} {{ interface.ip_address | netmask }}
 no shutdown
!
{% endfor %}
```

If a `<vendor>.j2` file exists, it overrides the embedded default.

## Programmatic use

```python
from scripts.netbox_client import NetBoxClient
from scripts.eveng_client import EVENGClient

nb = NetBoxClient("http://localhost:8000", "your-token")
devices = nb.get_devices()

eveng = EVENGClient("eveng.example.com", "admin", "secret", verify_ssl=False)
eveng.connect()
lab = eveng.create_lab("My-Lab", "Test lab")
node_id = eveng.create_node(lab, "R1", "vios", left=20, top=30)
eveng.start_all_nodes(lab)
```

## Development

### Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

With coverage:

```bash
pytest --cov=scripts --cov=orchestrator --cov-report=term-missing
```

The shipped suite covers the pure-logic helpers (config rendering filters, interface-name parsing, env-var loading). API-client paths that call NetBox / EVE-NG / Netmiko aren't covered yet — additions welcome.

### CI

Every push and pull request runs `pytest` against Python 3.10/3.11/3.12 and `pip-audit` against `requirements.txt`. See `.github/workflows/ci.yml`.

## Troubleshooting

### `docker compose` can't connect to the daemon / `Cannot connect to the Docker daemon`

The Docker daemon isn't running. Start Docker Desktop (macOS/Windows) or `sudo systemctl start docker` (Linux), then re-run `docker info` to confirm.

### NetBox not starting

```bash
docker compose logs netbox
docker compose restart netbox
```

### EVE-NG connection issues

- Use the web UI credentials (defaults are `admin` / `eve` for the community edition).
- Check the lab is not locked by another user.
- Verify the API is enabled.

### Device config failures

- Increase boot wait if devices are slow.
- Confirm management IPs match `topology.yml`.
- Verify SSH is enabled in the base image.

### EVE-NG provisioning fails to find the lab

The orchestrator opens an existing lab named `<lab.name>.unl`. Create the lab manually in the EVE-NG UI (File → New Lab) with the exact name from `topology.yml`, then re-run.

### NetBox API returns 401

`NETBOX_TOKEN` likely doesn't match the token NetBox actually issued. Either set it equal to `SUPERUSER_API_TOKEN`, or generate a fresh token under your user profile in NetBox and paste it into `.env`.

## Roadmap

1. Ansible dynamic inventory from NetBox
2. Batfish validation in CI
3. Streaming telemetry to InfluxDB / Grafana
4. Event-driven hooks via StackStorm

## License

[MIT](./LICENSE)
