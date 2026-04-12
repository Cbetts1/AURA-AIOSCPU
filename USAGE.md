# AURA-AIOSCPU — Usage Guide

## Starting AURA

```bash
# Universal mode (default — works everywhere)
python launch/launcher.py

# Explicit mode selection
AURA_MODE=universal python launch/launcher.py
AURA_MODE=internal  python launch/launcher.py
AURA_MODE=hardware  python launch/launcher.py
```

---

## AURA Shell

The interactive shell starts automatically when you run the launcher.

```
aura> help                 list all commands
aura> status               kernel state snapshot
aura> services             registered service states
aura> sysinfo              full JSON system snapshot
aura> device               hardware profile + compatibility
```

### AI Layer

```
aura> ask What services are running?
aura> ask What is the current memory usage?
aura> context              current AI context
aura> memory               recall stored memories
```

### Service Management

```
aura> start <service>      start a service
aura> stop <service>       stop a service
aura> restart <service>    restart a service
```

### Web Terminal

```
aura> web start            start the browser terminal (port 7331)
aura> web stop             stop the browser terminal
aura> web status           show web terminal status
```
Then open Chrome and navigate to: `http://localhost:7331`

### Build and Repair

```
aura> rebuild              rebuild rootfs from source
aura> repair               verify integrity + selective repair
aura> test                 run the test suite
aura> verify               check rootfs against build manifest
```

### Package Management

```
aura> pkg install <name>   install a Python package
aura> pkg list             list installed packages
```

---

## CLI Tool (`aura`)

After `pip install -e .`, the `aura` command is available system-wide:

```bash
aura status             kernel + services state
aura doctor             system + environment validation
aura build [--verify]   build rootfs from source
aura repair             verify integrity, rebuild if drift detected
aura verify             check rootfs against manifest
aura test [-k filter]   run unit tests
aura test --conformance run conformance suite
aura logs [--tail N]    show system logs
aura mirror             mirror/projection mode status
aura host               host-bridge capabilities
aura boot-log           last boot lifecycle
aura provenance         build time, commit, environment
aura override <action>  request a Command Override Layer (COL) override
```

---

## Virtual Network (Command Center Integration)

### Configure Command Center

Set the `CC_URL` environment variable to connect to your Command Center:

```bash
export CC_URL=http://192.168.1.10:8080
export CC_API_KEY=your-shared-secret
python launch/launcher.py
```

This node will:
1. Generate a stable UUID identity (`config/node_identity.json`)
2. Register with the Command Center
3. Send periodic heartbeats (every 30 seconds)
4. Accept remote commands from the CC

### Command Channel

The command channel REST API runs on port 7332 by default:

```bash
# Start with command channel enabled
CC_CHANNEL_HOST=0.0.0.0 CC_CHANNEL_PORT=7332 python launch/launcher.py
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/node/identity` | Node UUID, alias, capabilities |
| GET | `/api/node/status` | Live status snapshot |
| GET | `/api/node/capabilities` | Capability list |
| GET | `/api/node/metrics` | CPU, memory, uptime |
| GET | `/api/peers` | Known peer nodes |
| GET | `/api/services` | All service states |
| GET | `/api/health` | Health monitor report |
| GET | `/api/mesh/status` | Virtual mesh status |
| GET | `/api/logs` | Last 200 log lines |
| GET | `/api/version` | Version info |
| POST | `/api/node/announce` | Register a sibling peer |
| POST | `/api/cmd` | Execute a command |
| POST | `/api/service/start` | Start a service |
| POST | `/api/service/stop` | Stop a service |
| POST | `/api/mesh/sync` | Trigger peer state sync |
| POST | `/api/build/trigger` | Trigger rootfs rebuild |

**Authentication:**

Include `X-AURA-Key: <your_key>` header when `CC_API_KEY` is set.

**Examples:**

```bash
# Get node identity
curl http://localhost:7332/api/node/identity

# Execute a command
curl -X POST http://localhost:7332/api/cmd \
  -H "Content-Type: application/json" \
  -d '{"cmd": "status"}'

# Start a service
curl -X POST http://localhost:7332/api/service/start \
  -H "Content-Type: application/json" \
  -d '{"name": "network"}'

# With authentication
curl -H "X-AURA-Key: your-secret" http://localhost:7332/api/node/status
```

---

## Virtual Node Identity

Each AURA instance automatically creates a stable virtual identity:

```bash
cat config/node_identity.json
```
```json
{
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "alias": "myphonenodes-aura",
  "created_at": 1718000000.0
}
```

The node exposes these capabilities to the Command Center:
- `kernel.event_bus` — publish/subscribe event bus
- `kernel.scheduler` — task and job scheduling
- `services.health` — health monitoring and circuit breaker
- `services.cmd_channel` — remote REST command channel
- `vnet.node` — virtual network node
- `vnet.mesh` — peer mesh synchronisation
- `builder.module` — runtime module scaffolding
- _(and 15+ more)_

---

## Module Self-Expansion

AURA can scaffold new modules at runtime using the Module Builder:

### From the shell
```
aura> build module my_feature
aura> build plugin my_plugin
```

### Python API
```python
from services.module_builder import ModuleBuilder

mb = ModuleBuilder()

# Scaffold a new service
result = mb.scaffold_service(
    "analytics",
    description="Collects and reports usage analytics."
)
print(result.paths)
# ['services/analytics_service.py',
#  'tests/test_analytics_service.py',
#  'rootfs/etc/aura/services.d/analytics.service']

# Scaffold a shell plugin
result = mb.scaffold_plugin("greet", description="Greeting commands")
print(result.paths)
# ['shell/plugins/greet.py']
```

---

## Health Monitoring

The health monitor tracks all registered services and implements a
circuit-breaker pattern:

- **CLOSED** — service healthy, checks passing
- **OPEN** — too many consecutive failures, self-repair queued
- **HALF_OPEN** — repair submitted, awaiting confirmation

```bash
# Check health via REST
curl http://localhost:7332/api/health
```

---

## Logs

```bash
# Tail the main log
tail -f logs/aura.log

# View logs via CLI
aura logs --tail 50

# View logs via REST
curl http://localhost:7332/api/logs
```

---

## Advanced Configuration

Edit `config/default.json` to tune the kernel:

```json
{
  "kernel": {
    "tick_ms": 100,
    "max_memory_mb": 256,
    "max_task_queue": 256
  },
  "services": {
    "web_terminal": {"port": 7331},
    "command_channel": {"port": 7332}
  }
}
```

---

## Peer Network

Peers can be pre-configured in `config/peers.json`:

```json
[
  {
    "node_id": "550e8400-...",
    "alias": "server-aura",
    "host": "192.168.1.100",
    "port": 7332
  }
]
```

Or added at runtime:
```bash
curl -X POST http://localhost:7332/api/node/announce \
  -H "Content-Type: application/json" \
  -d '{"node_id": "abc-123", "alias": "server", "host": "192.168.1.100", "port": 7332}'
```
