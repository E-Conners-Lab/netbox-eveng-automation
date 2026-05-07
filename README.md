# NetBox-EVE-NG Automation Framework

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
- **Config generation**: Jinja2 templates for Cisco / Juniper / Arista
- **Config deployment**: pushes configs via SSH (Netmiko) or NETCONF (ncclient)

## Prerequisites

- Docker + Docker Compose
- Python 3.10+
- A reachable EVE-NG instance (community or pro)

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/<you>/netbox-eveng-automation.git
cd netbox-eveng-automation
pip install -r requirements.txt
```

### 2. Create your `.env`

```bash
cp .env.example .env
$EDITOR .env
```

Generate fresh values for `SECRET_KEY` and `SUPERUSER_API_TOKEN`:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))"
python -c "import secrets; print('SUPERUSER_API_TOKEN=' + secrets.token_hex(20))"
```

### 3. Start NetBox

```bash
docker compose up -d
```

Wait 2-3 minutes for NetBox to initialize, then visit `http://localhost:8000` and log in with the credentials from your `.env`.

### 4. Define your topology

Edit `topology.yml`. The shipped example uses RFC 5737 documentation IPs (`192.0.2.0/24`); change `management_network.gateway`, the per-device management IPs, and the `ntp_server` to match your real lab network.

### 5. Run the orchestrator

Full pipeline:

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

## Troubleshooting

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

## Roadmap

1. Ansible dynamic inventory from NetBox
2. Batfish validation in CI
3. Streaming telemetry to InfluxDB / Grafana
4. Event-driven hooks via StackStorm

## License

[MIT](./LICENSE)
