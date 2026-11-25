"""MCP server for FRC NetworkTables 4 (client).

Configuration (environment variables):
  NT_TEAM      FRC team number (default 2357). Resolves the roboRIO address.
  NT_HOST      Optional explicit server host/IP (e.g. "localhost" for simulation);
               overrides NT_TEAM when set.
  NT_PORT      Optional NT4 port (default 5810).
  NT_CLIENT_NAME  Client identity shown to the server (default "toolkit-mcp").

The team/host can also be changed at runtime with the `configure` tool.

Run: uv run mcps/networktables.py
"""

import os
import time
from collections.abc import Callable
from typing import Any

import ntcore
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_TEAM = 2357

mcp = MCPServer("networktables")
inst = ntcore.NetworkTableInstance.getDefault()

_state: dict[str, Any] = {
    "team": int(os.environ.get("NT_TEAM", DEFAULT_TEAM)),
    "host": os.environ.get("NT_HOST") or None,
    "port": int(os.environ.get("NT_PORT", ntcore.NetworkTableInstance.kDefaultPort4)),
    "started": False,
}
_publishers: dict[str, tuple[str, Any]] = {}  # topic name -> (type_str, publisher)

# NT type string -> ntcore.Value factory
_MAKERS: dict[str, Callable[[Any], Any]] = {
    "boolean": ntcore.Value.makeBoolean,
    "double": ntcore.Value.makeDouble,
    "float": ntcore.Value.makeFloat,
    "int": ntcore.Value.makeInteger,
    "string": ntcore.Value.makeString,
    "boolean[]": ntcore.Value.makeBooleanArray,
    "double[]": ntcore.Value.makeDoubleArray,
    "float[]": ntcore.Value.makeFloatArray,
    "int[]": ntcore.Value.makeIntegerArray,
    "string[]": ntcore.Value.makeStringArray,
    "raw": ntcore.Value.makeRaw,
}


def _connect() -> None:
    """(Re)point the client at the configured server and start it."""
    if _state["started"]:
        inst.stopClient()
        _publishers.clear()
    inst.startClient4(os.environ.get("NT_CLIENT_NAME", "toolkit-mcp"))
    if _state["host"]:
        inst.setServer(_state["host"], _state["port"])
    else:
        inst.setServerTeam(_state["team"], _state["port"])
    # NT4 only announces topics a client subscribes to; subscribe to everything.
    _state["sub"] = ntcore.MultiSubscriber(inst, [""])
    _state["started"] = True


def _ensure_started() -> None:
    if not _state["started"]:
        _connect()


def _wait_connected(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if inst.isConnected():
            return True
        time.sleep(0.05)
    return inst.isConnected()


def _jsonable(v: Any) -> Any:
    return (
        list(v)
        if isinstance(v, (list, tuple))
        else (v.hex() if isinstance(v, (bytes, bytearray)) else v)
    )


def _read(name: str, timeout: float) -> dict[str, Any]:
    _ensure_started()
    if not _wait_connected(timeout):
        raise ToolError(
            f"Not connected to NetworkTables server ({_target()}). "
            "Check robot/sim is running and the team/host configuration."
        )
    topic = inst.getTopic(name)
    # Topic announcements can lag the connection slightly.
    deadline = time.monotonic() + timeout
    while not topic.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not topic.exists():
        raise ToolError(f"Topic not found: {name}")
    entry = topic.getGenericEntry()
    # Allow the first value to arrive after subscribing.
    deadline = time.monotonic() + timeout
    val = entry.get()
    while (
        val.type() == ntcore.NetworkTableType.kUnassigned
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
        val = entry.get()
    return {
        "name": name,
        "type": topic.getTypeString(),
        "value": _jsonable(val.value()),
        "timestamp_us": val.time(),
    }


def _target() -> str:
    return _state["host"] or f"team {_state['team']}"


@mcp.tool()
def configure(team: int | None = None, host: str | None = None) -> dict[str, Any]:
    """Set the FRC team number and/or an explicit server host, then reconnect.

    team: FRC team number (default 2357) – resolves to the roboRIO address.
    host: explicit host/IP (e.g. "localhost" for robot simulation, "10.23.57.2").
          Pass an empty string to clear a previously set host.
    """
    if team is not None:
        _state["team"] = team
    if host is not None:
        _state["host"] = host or None
    _connect()
    return {"target": _target(), "team": _state["team"], "host": _state["host"]}


@mcp.tool()
def connection_status(wait_seconds: float = 2.0) -> dict[str, Any]:
    """Report whether we're connected to the NetworkTables server and to whom."""
    _ensure_started()
    connected = _wait_connected(wait_seconds)
    return {
        "connected": connected,
        "target": _target(),
        "connections": [
            {
                "remote_id": c.remote_id,
                "remote_ip": c.remote_ip,
                "protocol": c.protocol_version,
            }
            for c in inst.getConnections()
        ],
    }


@mcp.tool()
def list_topics(prefix: str = "/", timeout: float = 3.0) -> list[dict[str, str]]:
    """List topics (name and type) whose name starts with `prefix`.

    Example prefixes: "/" (everything), "/SmartDashboard/", "/FMSInfo/".
    """
    _ensure_started()
    if not _wait_connected(timeout):
        raise ToolError(f"Not connected to NetworkTables server ({_target()}).")
    time.sleep(0.3)  # let announcements arrive
    return sorted(
        (
            {"name": t.getName(), "type": t.getTypeString()}
            for t in inst.getTopics(prefix)
        ),
        key=lambda d: d["name"],
    )


@mcp.tool()
def get_value(name: str, timeout: float = 3.0) -> dict[str, Any]:
    """Read the current value of a topic, e.g. "/SmartDashboard/Gyro"."""
    return _read(name, timeout)


@mcp.tool()
def get_values(names: list[str], timeout: float = 3.0) -> list[dict[str, Any]]:
    """Read several topics at once. Missing topics return an `error` field."""
    out = []
    for n in names:
        try:
            out.append(_read(n, timeout))
        except ToolError as e:
            out.append({"name": n, "error": str(e)})
    return out


@mcp.tool()
def set_value(name: str, value: Any, type: str | None = None) -> dict[str, Any]:
    """Publish a value to a topic (creates the topic if needed).

    type: NT type string – one of boolean, double, float, int, string,
          boolean[], double[], float[], int[], string[]. If omitted, the
          existing topic's type is used, else it's inferred from the JSON
          value (bool→boolean, int/float→double, str→string, lists likewise).
    Note: setting a topic owned by robot code may be overwritten on its next loop.
    """
    _ensure_started()
    topic = inst.getTopic(name)
    if type is None:
        type = topic.getTypeString() if topic.exists() else _infer(value)
    if type not in _MAKERS:
        raise ToolError(f"Unsupported type '{type}'. Supported: {sorted(_MAKERS)}")
    if type == "raw":
        value = bytes.fromhex(value)
    cached = _publishers.get(name)
    if cached is None or cached[0] != type:
        cached = (type, topic.genericPublish(type))
        _publishers[name] = cached
    cached[1].set(_MAKERS[type](value))
    inst.flush()
    return {"name": name, "type": type, "value": value}


def _infer(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            raise ToolError("Cannot infer type of empty list; pass `type`.")
        return _infer(value[0]) + "[]"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "double"
    if isinstance(value, str):
        return "string"
    raise ToolError(f"Cannot infer NT type for {value!r}; pass `type`.")


@mcp.tool()
def unpublish(name: str) -> dict[str, Any]:
    """Stop publishing a topic previously created with set_value."""
    # ntcore publishers have no close(); dropping the last reference releases the handle.
    cached = _publishers.pop(name, None)
    unpublished = cached is not None
    del cached
    return {"name": name, "unpublished": unpublished}


if __name__ == "__main__":
    mcp.run()
