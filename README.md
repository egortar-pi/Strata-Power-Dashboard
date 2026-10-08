# AI Power Dashboard ⚡

**Self-hosted NVIDIA GPU energy and Strata token monitoring for Linux AI workstations.**

Track multiple NVIDIA GPUs, estimated whole-system energy usage, electricity bills, and the API-equivalent value of tokens generated locally — using a lightweight Python web dashboard. Designed for always-on LLM servers running tools such as Strata and OpenCode.

**No Docker, Nginx, cloud account, JavaScript build tools, or Python packages required.**

## Currency settings

Select **Settings → Currency (all prices)** once (default: **EUR**). All monetary fields use that currency:

- **Electricity rate per kWh:** numeric only, e.g. `0.25`.
- **API input/output price per 1M tokens:** numeric only, entered in the same currency.
- Dashboard costs and the API-minus-electricity comparison display numbers; the currency is indicated once in the dashboard header.

**No automatic exchange-rate conversion:** if you switch currency, update electricity and API numeric prices yourself. This avoids mixing USD-priced APIs with EUR electricity.

## Features

- **Multi-GPU power monitoring:** per-GPU watts, utilization, VRAM and energy (kWh) from `nvidia-smi`, identified by GPU UUID.
- **Estimated wall power:** GPU readings + configurable CPU idle/load estimates + motherboard/RAM/storage/fans estimate, adjusted for PSU efficiency.
- **Electricity costs:** editable price per kWh with one global currency (EUR by default), plus historical energy totals.
- **Strata token analytics:** input (`totals.prompt_tokens`), output (`totals.output_tokens`) and reused/cached input (`totals.reused`), using cumulative counter deltas.
- **API cost comparison:** editable input/output prices per million tokens in the same global currency. This is a *hypothetical API-equivalent cost*, **not** a precise comparison with subscription plans or model quality.
- **Historical SQLite storage:** 24h, 7d, 30d and all-time reporting, surviving reboots and service restarts.
- **Live web UI:** auto-updates every 5 seconds, with a power chart, GPU details and settings.
- **Boot-time startup:** optional `systemd` service.

## Requirements

- Ubuntu or another Linux distribution with Python 3.9+ and `systemd` (for the installer).
- Working proprietary NVIDIA driver and `nvidia-smi`, with power reporting supported by the installed GPUs.
- Optional Strata HTTP metrics endpoint returning JSON (default: `http://127.0.0.1:8080/metrics`).

> **Hardware notes:** The initial CPU/board defaults are illustrative estimates for an Intel Core i7-6850K / X99 workstation: CPU idle **25 W**, CPU busy **110 W**, other components **55 W**, PSU efficiency **88%**. They are *not hardware measurements*. Intel's CPU TDP is not equal to actual wall power. For accurate whole-PC costs, use a calibrated wall power meter or smart plug. This project does not yet integrate smart plugs.

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/ai-power-dashboard.git
cd ai-power-dashboard
nvidia-smi  # Verify the driver and all cards first
chmod +x install.sh
./install.sh
```

Open the dashboard from the same machine at **http://127.0.0.1:8092**.

For remote access from Windows (recommended):

```powershell
ssh -N -L 8092:127.0.0.1:8092 USER@SERVER_IP
```

Then open **http://127.0.0.1:8092** on Windows. The collector continues running if the SSH tunnel closes.

## Accessing the dashboard from your local network (LAN)

By default, the dashboard binds to `127.0.0.1:8092`, so it can only be opened locally or through an SSH tunnel. If you want to open it from another computer on your trusted LAN, bind the web server to `0.0.0.0` instead.

### 1. Change the systemd listening address

Open the installed service:

```bash
sudo systemctl edit ai-power-dashboard
```

Add this override (it preserves the rest of the installed service):

```ini
[Service]
Environment="AI_DASH_HOST=0.0.0.0"
```

> `0.0.0.0` means **all network interfaces**, not only your LAN. The default port remains `8092`. The application reads `AI_DASH_HOST` from the environment.

### 2. Apply and verify

```bash
sudo systemctl daemon-reload
sudo systemctl restart ai-power-dashboard
sudo ss -lntp | grep 8092
```

The listening address should be `0.0.0.0:8092`. Check the API locally:

```bash
curl -fsS http://127.0.0.1:8092/api/health
```

### 3. Allow only your LAN through the firewall (if UFW is enabled)

For example, if your LAN is `192.168.0.0/24`:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8092 proto tcp
```

Replace this subnet with your actual network. Check `sudo ufw status` first; if managing the server remotely, ensure your SSH access is allowed before making firewall changes. A firewall rule is necessary to restrict exposure because binding to `0.0.0.0` itself does not restrict access to the LAN.

### 4. Open it from another device

```text
http://SERVER_LAN_IP:8092
```

For example: `http://192.168.0.152:8092` (replace with your server's IP).

**Security warning:** This dashboard currently has **no login/authentication** and can change its settings through the web API. Use `0.0.0.0` only on a trusted network with appropriate firewall restrictions; do **not** forward port `8092` from your router or expose it to the public internet. For untrusted networks, use the default `127.0.0.1` binding with an SSH tunnel or VPN instead.

To revert to localhost-only mode, remove the `AI_DASH_HOST=0.0.0.0` override, then reload systemd and restart the service.

### Manual run (without systemd)

```bash
python3 app.py serve
# Other terminal: python3 app.py report --period 7d
```

## Configuration

Open **Settings** in the dashboard to edit:

| Setting | Default | Meaning |
| --- | --- | --- |
| Electricity rate | 0.25 EUR/kWh | Cost per kWh in the globally selected currency |
| CPU idle / busy | 25 / 110 W | Approximate CPU power range |
| Other components | 55 W | Motherboard, memory, storage and fans |
| PSU efficiency | 0.88 | Assumed DC-to-AC efficiency |
| Strata metrics URL | `http://127.0.0.1:8080/metrics` | Loopback HTTP JSON endpoint |
| Input / output JSON paths | `totals.prompt_tokens` / `totals.output_tokens` | Cumulative token counters |
| Input / output API rates | $3 / $15 per million | **Examples only**, change to chosen comparison rates |
| Poll interval | 5 seconds | GPU and Strata collection cadence |

Strata's cached/reused input token counter is read from `totals.reused`. Reused tokens are *already included* in prompt tokens; never add them a second time. Current API comparison treats all prompt tokens equally and does not apply cached-token discounts.

Changes to the electricity rate recalculate the displayed **historical** energy cost using the *current* rate, not the rate applicable when the electricity was consumed. For time-of-use tariffs or historical tariff changes, a rate-history feature would be needed.

## Data and calculations

**GPU power:** queried from `nvidia-smi` for every discovered GPU. Adjacent samples are integrated using the trapezoidal rule (W × elapsed time → kWh). Power is not reconstructed through monitoring outages; gaps beyond two sampling intervals are capped.

**Estimated system power:**

```text
CPU_W = CPU_IDLE_W + CPU_utilization * (CPU_BUSY_W - CPU_IDLE_W)
WALL_W ≈ (SUM(GPU_W) + CPU_W + OTHER_W) / PSU_EFFICIENCY
ENERGY_COST = SYSTEM_KWH * ELECTRICITY_PRICE_PER_KWH
```

CPU utilization comes from `/proc/stat`, not package power telemetry. If GPU power is unavailable, the collector logs a warning and pauses whole-system energy accumulation rather than falsely treating GPU use as zero. This conservative accounting **undercounts** electricity during outages; review error messages and restore `nvidia-smi` to resume measurements.

**Token counts:** cumulative Strata counters are differenced at each poll. On the initial observation or a counter reset/restart, a new baseline is created. Tokens generated *before* monitoring started are not backfilled or invented.

**GPU identification:** the NVIDIA UUID is used to keep card histories consistent even when index ordering changes after reboot.

**Storage:** SQLite lives in `~/.local/share/ai-power-dashboard/history.sqlite3` for the service user, unless `AI_DASH_DIR` is configured. Protect it as potentially sensitive operational data.

## Operations

```bash
sudo systemctl status ai-power-dashboard
sudo systemctl restart ai-power-dashboard
journalctl -u ai-power-dashboard -f
python3 app.py sample
python3 app.py report --period 7d
python3 -m unittest discover -s tests -v
```

To choose a different binding or port, edit the service's `Environment=AI_DASH_HOST=127.0.0.1` / `Environment=AI_DASH_PORT=8092` entries, then `sudo systemctl daemon-reload && sudo systemctl restart ai-power-dashboard`.

## Security

**No authentication is built in.** Settings can be changed via the API. By default the dashboard listens **only on `127.0.0.1`**. Use SSH port forwarding or a trusted VPN. Binding to `0.0.0.0` exposes it to the network: only do so in a fully trusted LAN, restrict ingress with a firewall, and do not forward its port to the public internet.

The dashboard does not collect prompts, responses or API keys, but may store filenames, GPU identifiers, operational timestamps and usage history. Do not commit the SQLite database or private configuration.

## Troubleshooting

**`Failed to initialize NVML: Driver/library version mismatch`** means the loaded NVIDIA kernel driver does not match the userspace library. After a driver upgrade, a *planned reboot* often resolves this. Check `nvidia-smi` before troubleshooting the dashboard itself.

**Strata tokens stay at zero:** verify `curl http://127.0.0.1:8080/metrics` and inspect the `totals` object. The first successful poll establishes a baseline, so prior requests are not included.

**Currency:** Settings contains one global `Currency` selector, defaulting to `EUR`. Electricity and API price fields accept numbers only. Both are interpreted in that currency and compared directly. No exchange conversion takes place. Changing the currency selector does not convert previously entered prices: update the numeric rates to match the newly selected currency.

## Limitations / roadmap

- CPU, motherboard, RAM and PSU consumption are estimated; wall-meter integration is not implemented.
- If any GPU reading fails, the affected collection interval can be missing from cost totals.
- Dashboard reports *all* energy used by the monitored workstation, not energy attributable specifically to one AI job.
- The Strata collector currently reads **one** Strata endpoint. Other OpenCode backends require separate integrations.
- Subscription savings, break-even analyses, cached-token API pricing, multi-engine accounting and tariff history are potential future improvements.

## Contributing / license

See [CONTRIBUTING.md](CONTRIBUTING.md). Distributed under the [MIT License](LICENSE).

## Stability and existing installations

The collector retries after temporary SQLite errors, including failures to read its
sampling interval. The health endpoint `/api/health` checks database availability;
`/api/data` returns HTTP 503 instead of abruptly dropping the connection on a DB
failure. Older `NULL` samples remain in the database and are not treated as 0 W.

Configuration uses `AI_DASH_DIR` for data directory and optional `AI_DASH_DB` for
the complete database filename. Default: `~/.local/share/ai-power-dashboard/history.sqlite3`.
Existing installations should preserve their established path to avoid starting a new
empty database. The installer preserves an existing systemd service and thus its LAN
binding. Its new-service template binds to `127.0.0.1` for safety.

Before updating a running installation, stop the service and back up the database
with Python's SQLite backup API (rather than copying only the main .sqlite3 file
while WAL mode is in use). Keep the backup outside `/opt/ai-power-dashboard`.

To update only the Python code and UI after backing up, copy `app.py` and
`index.html` to `/opt/ai-power-dashboard/` and restart the service. Existing
settings and SQLite history remain under the configured data directory.

**Note:** this dashboard is unauthenticated. Do not expose it to the Internet.
