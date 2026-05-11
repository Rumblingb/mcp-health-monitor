"""
MCP Health Monitor Server
Checks if MCP servers and HTTP endpoints are up and responsive.
"""
import asyncio
import time
import subprocess
import sys
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


server = Server("mcp-health-monitor")


def _parse_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="check_server",
            description="Ping a URL and report status code, response time, content-type, and server header.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to check"},
                    "timeout": {
                        "type": "number",
                        "description": "Request timeout in seconds (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="check_mcp_server",
            description="Try to start an MCP server process and check if it responds to initialization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command to start the MCP server (e.g., 'python', 'node', 'uvx')",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Arguments for the command",
                        "default": [],
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="batch_check",
            description="Check multiple URLs in parallel and return all results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to check concurrently",
                    }
                },
                "required": ["urls"],
            },
        ),
        Tool(
            name="check_endpoint",
            description="Full HTTP check with timing breakdown (DNS, connect, TLS, response).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to check"},
                    "expected_status": {
                        "type": "integer",
                        "description": "Expected HTTP status code (default: None)",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


async def _do_http_get(url: str, timeout: float = 10.0) -> dict:
    """Perform a simple HTTP GET and return result dict."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        t0 = time.monotonic()
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.TimeoutException:
            return {"error": f"Request timed out after {_parse_duration(timeout)}"}
        except httpx.ConnectError as e:
            return {"error": f"Connection failed: {e}"}
        except Exception as e:
            return {"error": str(e)}

        elapsed = time.monotonic() - t0
        return {
            "url": url,
            "status_code": resp.status_code,
            "response_time": _parse_duration(elapsed),
            "response_time_seconds": round(elapsed, 3),
            "content_type": resp.headers.get("content-type", "N/A"),
            "server": resp.headers.get("server", "N/A"),
            "headers": dict(resp.headers),
        }


def _do_http_get_with_timing(url: str, expected_status: Optional[int] = None) -> dict:
    """Perform HTTP GET with per-phase timing breakdown using httpx internals."""
    import socket
    import ssl
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or url
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    # Resolve DNS
    t_dns_start = time.monotonic()
    try:
        addrs = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addr = addrs[0][4]
    except socket.gaierror as e:
        return {"error": f"DNS resolution failed: {e}"}
    t_dns = time.monotonic() - t_dns_start

    # TCP connect
    t_conn_start = time.monotonic()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(addr)
    except Exception as e:
        sock.close()
        return {"error": f"TCP connect failed: {e}"}
    t_conn = time.monotonic() - t_conn_start

    tls_time = 0.0
    tls_version = None
    if parsed.scheme == "https":
        t_tls_start = time.monotonic()
        try:
            context = ssl.create_default_context()
            sock_tls = context.wrap_socket(sock, server_hostname=host)
            tls_version = sock_tls.version()
        except Exception as e:
            sock.close()
            return {"error": f"TLS handshake failed: {e}"}
        tls_time = time.monotonic() - t_tls_start
    else:
        sock_tls = sock

    # HTTP request
    t_http_start = time.monotonic()
    try:
        sock_tls.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
        )
        data = b""
        while True:
            chunk = sock_tls.recv(4096)
            if not chunk:
                break
            data += chunk
    except Exception as e:
        sock_tls.close()
        return {"error": f"HTTP request failed: {e}"}
    t_http = time.monotonic() - t_http_start

    sock_tls.close()

    # Parse headers
    header_end = data.find(b"\r\n\r\n")
    if header_end == -1:
        return {"error": "No valid HTTP response received"}
    raw_headers = data[:header_end].decode("utf-8", errors="replace")
    body = data[header_end + 4 :]

    lines = raw_headers.split("\r\n")
    status_line = lines[0] if lines else ""
    status_code = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 0

    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    total_time = t_dns + t_conn + tls_time + t_http

    result = {
        "url": url,
        "status_code": status_code,
        "content_type": headers.get("content-type", "N/A"),
        "server": headers.get("server", "N/A"),
        "total_time": _parse_duration(total_time),
        "total_time_seconds": round(total_time, 3),
        "timing": {
            "dns": _parse_duration(t_dns),
            "dns_seconds": round(t_dns, 4),
            "connect": _parse_duration(t_conn),
            "connect_seconds": round(t_conn, 4),
            "tls": _parse_duration(tls_time),
            "tls_seconds": round(tls_time, 4),
            "tls_version": tls_version,
            "response": _parse_duration(t_http),
            "response_seconds": round(t_http, 4),
        },
        "body_size": len(body),
    }

    if expected_status is not None and status_code != expected_status:
        result["status_match"] = False
        result["expected_status"] = expected_status
    elif expected_status is not None:
        result["status_match"] = True
        result["expected_status"] = expected_status

    return result


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "check_server":
        url = arguments["url"]
        timeout = arguments.get("timeout", 10.0)
        result = await _do_http_get(url, timeout)
        return [TextContent(type="text", text=_format_result(result))]

    elif name == "check_mcp_server":
        command = arguments["command"]
        args = arguments.get("args", [])

        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Send MCP init message
            init_msg = (
                '{"jsonrpc":"2.0","id":1,"method":"initialize",'
                '"params":{"protocolVersion":"2024-11-05",'
                '"capabilities":{},"clientInfo":{"name":"health-monitor","version":"1.0.0"}}}\n'
            )
            stdout, stderr = proc.communicate(input=init_msg.encode(), timeout=15)
            runtime = time.monotonic() - t0

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if '"result"' in stdout_str or '"jsonrpc"' in stdout_str:
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"✅ MCP server '{command}' responded successfully\n"
                            f"Runtime: {_parse_duration(runtime)}\n"
                            f"Stdout: {_truncate(stdout_str, 2000)}\n"
                            f"Stderr: {_truncate(stderr_str, 2000)}"
                        ),
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"❌ MCP server '{command}' did not return a valid response\n"
                            f"Runtime: {_parse_duration(runtime)}\n"
                            f"Stdout: {_truncate(stdout_str, 2000)}\n"
                            f"Stderr: {_truncate(stderr_str, 2000)}"
                        ),
                    )
                ]

        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            runtime = time.monotonic() - t0
            return [
                TextContent(
                    type="text",
                    text=(
                        f"❌ MCP server '{command}' timed out after {_parse_duration(runtime)}\n"
                        f"Stderr: {_truncate(stderr.decode('utf-8', errors='replace'), 2000)}"
                    ),
                )
            ]
        except FileNotFoundError:
            return [
                TextContent(
                    type="text",
                    text=f"❌ Command not found: '{command}'",
                )
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"❌ Error running MCP server '{command}': {e}",
                )
            ]

    elif name == "batch_check":
        urls = arguments["urls"]
        tasks = [_do_http_get(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        lines = ["# Batch Check Results", f"Checked {len(urls)} URLs\n"]
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                lines.append(f"❌ {url}: {result}")
            else:
                lines.append(f"✅ {url}: {result.get('status_code', '?')} | {result.get('response_time', '?')}")
        lines.append(f"\nCheck complete — {_count_success(results)}/{len(urls)} succeeded")
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "check_endpoint":
        url = arguments["url"]
        expected_status = arguments.get("expected_status")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_http_get_with_timing, url, expected_status)
        return [TextContent(type="text", text=_format_timing_result(result))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def _count_success(results: list) -> int:
    count = 0
    for r in results:
        if isinstance(r, dict) and r.get("status_code"):
            count += 1
    return count


def _truncate(text: str, max_len: int = 2000) -> str:
    if len(text) > max_len:
        return text[:max_len] + f"\n... (truncated, {len(text)} total chars)"
    return text


def _format_result(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['url']}: {r['error']}"
    return (
        f"✅ {r['url']}\n"
        f"   Status: {r['status_code']}\n"
        f"   Response Time: {r['response_time']}\n"
        f"   Content-Type: {r['content_type']}\n"
        f"   Server: {r['server']}"
    )


def _format_timing_result(r: dict) -> str:
    if "error" in r:
        return f"❌ {r.get('url', '?')}: {r['error']}"
    lines = [f"✅ {r['url']}"]
    lines.append(f"   Status: {r['status_code']} | {r.get('content_type', 'N/A')}")
    if "expected_status" in r:
        match = "✅" if r.get("status_match") else "❌"
        lines.append(f"   Expected Status: {r['expected_status']} {match}")
    lines.append(f"   Total Time: {r['total_time']}")
    t = r.get("timing", {})
    lines.append(f"   ⏱  DNS: {t.get('dns', 'N/A')}")
    lines.append(f"      Connect: {t.get('connect', 'N/A')}")
    if t.get("tls_version"):
        lines.append(f"      TLS ({t['tls_version']}): {t.get('tls', 'N/A')}")
    else:
        lines.append(f"      TLS: {t.get('tls', 'N/A')}")
    lines.append(f"      Response: {t.get('response', 'N/A')}")
    lines.append(f"   Server: {r.get('server', 'N/A')}")
    lines.append(f"   Body Size: {r.get('body_size', 'N/A')} bytes")
    return "\n".join(lines)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
