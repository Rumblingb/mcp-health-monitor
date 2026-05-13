# MCP Health Monitor

An MCP server that checks if HTTP endpoints and MCP servers are up and responsive.

**$19/mo** — Subscribe at: [https://buy.stripe.com/aFafZj0qXck4bY43IL1oI0F](https://buy.stripe.com/aFafZj0qXck4bY43IL1oI0F)

---

## Tools

### 1. `check_server(url, timeout?)`
Ping a URL and report status code, response time, content-type, and server header.

- `url` (string, required) — URL to check
- `timeout` (number, optional, default: 10) — Request timeout in seconds

**Returns:** Status code, response time, content-type, server header, full response headers.

### 2. `check_mcp_server(command, args?)`
Start an MCP server process and verify it responds to the MCP initialization handshake.

- `command` (string, required) — Command to run (e.g., `python`, `node`, `uvx`)
- `args` (array of strings, optional) — Command-line arguments

**Returns:** Success/failure indicator, runtime, stdout, stderr.

### 3. `batch_check(urls[])`
Check multiple URLs concurrently and return all results at once.

- `urls` (array of strings, required) — List of URLs to check in parallel

**Returns:** Summary per URL plus success/total count.

### 4. `check_endpoint(url, expected_status?)`
Full HTTP check with per-phase timing breakdown.

- `url` (string, required) — URL to check
- `expected_status` (integer, optional) — Expected HTTP status code for validation

**Returns:** DNS time, TCP connect time, TLS handshake time + version, HTTP response time, total time, body size, and status match verification.

### 5. `check_smithery(namespace)`
Fetch all servers from a Smithery namespace and check if their endpoints respond.

- `namespace` (string, required) — Smithery namespace (e.g., `@anthropic`, `@openai`)

**Returns:** Per-server health status, namespace health percentage, free checks remaining.

### 6. `monitor_add(url, interval?)`
Add a server URL to the monitoring list with a check interval.

- `url` (string, required) — URL of the server to monitor
- `interval` (number, optional, default: 60, min: 30) — Check interval in seconds

**Returns:** Confirmation with initial check result and free checks remaining.

### 7. `monitor_status()`
Return the status of all currently monitored servers.

**Returns:** List of monitored servers with their last status, interval, and last check time.

---

## Rate Limiting

- **Free tier:** 20 checks per instance lifetime
- **Pro tier ($19/mo):** Unlimited checks
- Rate limit applies to `check_server`, `check_mcp_server`, `batch_check`, `check_endpoint`, and `check_smithery`
- `monitor_add` and `monitor_status` do not consume check credits

---

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### As a standalone MCP server (stdio transport)

```bash
python server.py
```

Configure in your MCP client (e.g., Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "mcp-health-monitor": {
      "command": "python",
      "args": ["/path/to/mcp-health-monitor/server.py"]
    }
  }
}
```

### Example queries

> "Is example.com up?"
> "Check if my MCP server at /usr/bin/uvx -- mcp-kubernetes is working"
> "Batch check these 5 endpoints"
> "Do a full endpoint timing breakdown on api.example.com expecting status 200"
> "Check all servers in the @anthropic Smithery namespace"
> "Monitor api.example.com every 60 seconds"
> "Show me the status of all monitored servers"

---

## Requirements

- Python 3.10+
- mcp >= 1.0.0
- httpx >= 0.27.0

---

## License

MIT
