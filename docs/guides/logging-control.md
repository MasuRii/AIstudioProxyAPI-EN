# Log Control Guide

This document describes how to control the logging verbosity and behavior of the project.

## Log System Overview

The project contains two main logging systems:

1. **Launcher Logs** (`launch_camoufox.py`)
2. **Main Server Logs** (`server.py`)

## Launcher Log Control

### Log File Location

- File Path: `logs/launch_app.log`
- Log Level: Usually `INFO`
- Content: Startup and coordination process, and output from the internally started Camoufox process

### Configuration

The launcher's log level is set internally in the script via `setup_launcher_logging(log_level=logging.INFO)`.

## Main Server Log Control

### Log File Location

- File Path: `logs/app.log`
- Configuration Module: `logging_utils/setup.py`
- Content: Detailed runtime logs of FastAPI server

### Environment Variable Control

Main server logs are primarily controlled via **environment variables**, which are set by `launch_camoufox.py` before starting the main server:

#### SERVER_LOG_LEVEL

Controls the level of the main server logger (`AIStudioProxyServer`).

- **Default**: `INFO`
- **Allowed Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Usage Example**:

```bash
# Linux/macOS
export SERVER_LOG_LEVEL=DEBUG
python launch_camoufox.py --headless

# Windows (cmd)
set SERVER_LOG_LEVEL=DEBUG
python launch_camoufox.py --headless

# Windows (PowerShell)
$env:SERVER_LOG_LEVEL="DEBUG"
python launch_camoufox.py --headless
```

#### SERVER_REDIRECT_PRINT

Controls the behavior of `print()` and `input()` inside the main server.

- **`'true'`**: `print()` output is redirected to logging system, `input()` might be unresponsive (Default for headless mode)
- **`'false'`**: `print()` outputs to original terminal, `input()` waits for user input in terminal (Default for debug mode)

#### DEBUG_LOGS_ENABLED

Controls whether detailed debug log points for specific internal functions of the main server are activated.

- **Default**: `false`
- **Allowed Values**: `true`, `false`

**Usage Example**:

```bash
# Linux/macOS
export DEBUG_LOGS_ENABLED=true
python launch_camoufox.py --headless

# Windows (cmd)
set DEBUG_LOGS_ENABLED=true
python launch_camoufox.py --headless

# Windows (PowerShell)
$env:DEBUG_LOGS_ENABLED="true"
python launch_camoufox.py --headless
```

#### TRACE_LOGS_ENABLED

Controls deeper level tracing logs.

- **Default**: `false`
- **Allowed Values**: `true`, `false`
- **Note**: Usually not needed unless for deep debugging

**Usage Example**:

```bash
# Linux/macOS
export TRACE_LOGS_ENABLED=true
python launch_camoufox.py --headless

# Windows (cmd)
set TRACE_LOGS_ENABLED=true
python launch_camoufox.py --headless

# Windows (PowerShell)
$env:TRACE_LOGS_ENABLED="true"
python launch_camoufox.py --headless
```

## Combination Examples

### Enable Detailed Debug Logs

```bash
# Linux/macOS
export SERVER_LOG_LEVEL=DEBUG
export DEBUG_LOGS_ENABLED=true
python launch_camoufox.py --headless --server-port 2048

# Windows (PowerShell)
$env:SERVER_LOG_LEVEL="DEBUG"
$env:DEBUG_LOGS_ENABLED="true"
python launch_camoufox.py --headless --server-port 2048
```

### Enable Most Detailed Trace Logs

```bash
# Linux/macOS
export SERVER_LOG_LEVEL=DEBUG
export DEBUG_LOGS_ENABLED=true
export TRACE_LOGS_ENABLED=true
python launch_camoufox.py --headless

# Windows (PowerShell)
$env:SERVER_LOG_LEVEL="DEBUG"
$env:DEBUG_LOGS_ENABLED="true"
$env:TRACE_LOGS_ENABLED="true"
python launch_camoufox.py --headless
```

## Log Viewing Methods

### File Logs

- `logs/app.log`: Detailed logs for FastAPI server
- `logs/launch_app.log`: Launcher logs
- File logs usually contain more detailed information than terminal or Web UI

### Real-time Logs (WebSocket)

Besides files and terminal, you can get real-time log streams via WebSocket. This is applied in the right sidebar of Web UI.

- **Endpoint**: `/ws/logs` (e.g. `ws://127.0.0.1:2048/ws/logs`)
- **Function**: Push real-time logs of `INFO` and above levels from main server
- **Format**: Plain text log lines, consistent with `app.log` format
- **Usage**: For display in Web UI or integration into external monitoring systems

### Web UI Logs

- Web UI right sidebar integrates the above WebSocket feature
- Real-time display of logs from main server
- Provides button to clear logs

### Terminal Logs

- In debug mode (`--debug`), logs are directly output to the starting terminal
- In headless mode, terminal logs are fewer, main information is in log files

## Log Level Explanation

### DEBUG

- Most detailed log information
- Includes function calls, variable values, execution flow, etc.
- Used for deep debugging and troubleshooting

### INFO

- General information logs
- Includes important operations and state changes
- Default level for daily operation

### WARNING

- Warning information
- Indicates potential problems or abnormal situations
- Does not affect normal function but needs attention

### ERROR

- Error information
- Indicates functional abnormality or failure
- Needs immediate attention and handling

### CRITICAL

- Severe error
- Indicates system-level serious problems
- May lead to service unavailability

## Performance Considerations

### Impact of Log Level on Performance

- **DEBUG Level**: Generates massive logs, may affect performance, use only when debugging
- **INFO Level**: Balances information quantity and performance, suitable for daily operation
- **WARNING and above**: Least logs, minimal performance impact

### Log File Size Management

- Log files grow over time, regular cleaning or rotation is recommended
- Old log files can be manually deleted
- Consider using system log rotation tools (like logrotate)

## Troubleshooting

### Logs Not Showing

1. Check if environment variables are set correctly
2. Confirm log file path is writable
3. Check if Web UI WebSocket connection is normal

### Too Many Logs

1. Lower log level (e.g. from DEBUG to INFO)
2. Disable DEBUG_LOGS_ENABLED and TRACE_LOGS_ENABLED
3. Regularly clean log files

### Missing Important Logs

1. Raise log level (e.g. from WARNING to INFO or DEBUG)
2. Enable DEBUG_LOGS_ENABLED to get more debug info
3. Check log files instead of just terminal output

## Best Practices

### Daily Operation

```bash
# Recommended daily operation config
export SERVER_LOG_LEVEL=INFO
python launch_camoufox.py --headless
```

### Debugging Issues

```bash
# Recommended debug config
export SERVER_LOG_LEVEL=DEBUG
export DEBUG_LOGS_ENABLED=true
python launch_camoufox.py --debug
```

### Production Environment

```bash
# Recommended production environment config
export SERVER_LOG_LEVEL=WARNING
python launch_camoufox.py --headless
```

## Next Steps

After log control configuration is complete, please refer to:

- [Troubleshooting Guide](troubleshooting.md)
- [Advanced Configuration Guide](advanced-configuration.md)
