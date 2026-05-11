# MCP Health Monitor

An MCP server that checks if HTTP endpoints and MCP servers are up and responsive.

**$19/mo** — Subscribe at: [https://buy.stripe.com/dRm6oJ4Hd2Jugek0wz1oI0m](https://buy.stripe.com/dRm6oJ4Hd2Jugek0wz1oI0m)

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

---

## Requirements

- Python 3.10+
- mcp >= 1.0.0
- httpx >= 0.27.0

---

## License

MIT
