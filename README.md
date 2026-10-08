# AI Power Dashboard ⚡

**Self-hosted NVIDIA GPU energy and Strata token monitoring for Linux AI workstations.**

Track multiple NVIDIA GPUs, estimated whole-system energy usage, electricity bills, and the API-equivalent value of tokens generated locally — using a lightweight Python web dashboard. Designed for always-on LLM servers running tools such as Strata and OpenCode.

**No Docker, Nginx, cloud account, JavaScript build tools, or Python packages required.**

## Features

- **Multi-GPU power monitoring:** per-GPU watts, utilization, VRAM and energy (kWh) from `nvidia-smi`, identified by GPU UUID.
- **Estimated wall power:** GPU readings + configurable CPU idle/load estimates + motherboard/RAM/storage/fans estimate, adjusted for PSU efficiency.
- **Electricity costs:** editable price per kWh and currency, plus historical energy totals.
- **Strata token analytics:** input (`totals.prompt_tokens`), output (`totals.output_tokens`) and reused/cached input (`totals.reused`), using cumulative counter deltas.
- **API cost comparison:** editable USD input/output prices per million tokens. This is a *hypothetical API-equivalent cost*, **not** a precise comparison with subscription plans or model quality.
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

## 🌐 Accessing the Dashboard over LAN

By default, AI Power Dashboard listens on `127.0.0.1:8092`, meaning it is only accessible from the machine on which it is running.

To access the dashboard from other devices on your local network, change the listening address to `0.0.0.0`.

### 1. Update the systemd service

Open the service configuration:

```bash
sudo nano /etc/systemd/system/ai-power-dashboard.service
```

In the `[Service]` section, set:

```ini
Environment=HOST=0.0.0.0
```

> **Note:** This assumes your installation reads the `HOST` environment variable. If the application uses a command-line argument instead, change its host argument to `--host 0.0.0.0`.

### 2. Restart the service

```bash
sudo systemctl daemon-reload
sudo systemctl restart ai-power-dashboard
```

Verify that the dashboard is listening on all network interfaces:

```bash
sudo ss -lntp | grep 8092
```

Expected output should include:

```text
0.0.0.0:8092
```

### 3. Configure the firewall (optional)

If UFW is enabled, allow access from your local network:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8092 proto tcp
```

Replace `192.168.0.0/24` with your actual LAN subnet.

### 4. Open the dashboard

From another device on your network, visit:

```text
http://YOUR_SERVER_IP:8092
```

For example:

```text
http://192.168.0.152:8092
```

### 🔒 Security Notice

**Binding to `0.0.0.0` makes the dashboard accessible through all network interfaces, not just your LAN.**

The dashboard does not currently provide built-in authentication, and its settings can be modified through the web interface.

- Use this configuration only on trusted networks.
- Restrict access using firewall rules.
- Do not expose port `8092` directly to the public internet.
- For remote access, prefer SSH tunneling, Tailscale, or a secured reverse proxy.

For maximum security, keep the default `127.0.0.1` binding and access the dashboard through an SSH tunnel.

### Manual run (without systemd)

```bash
python3 app.py serve
# Other terminal: python3 app.py report --period 7d
```

## Configuration

Open **Settings** in the dashboard to edit:

| Setting | Default | Meaning |
| --- | --- | --- |
| Electricity rate | 0.25 EUR/kWh | Cost per kWh (choose your currency) |
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

**API-equivalent value vs electricity mismatch:** API comparisons are priced in USD; electricity is shown in your chosen currency. No exchange rate is assumed or silently applied.

## Limitations / roadmap

- CPU, motherboard, RAM and PSU consumption are estimated; wall-meter integration is not implemented.
- If any GPU reading fails, the affected collection interval can be missing from cost totals.
- Dashboard reports *all* energy used by the monitored workstation, not energy attributable specifically to one AI job.
- The Strata collector currently reads **one** Strata endpoint. Other OpenCode backends require separate integrations.
- Subscription savings, break-even analyses, cached-token API pricing, multi-engine accounting and tariff history are potential future improvements.

## Contributing / license

See [CONTRIBUTING.md](CONTRIBUTING.md). Distributed under the [MIT License](LICENSE).
