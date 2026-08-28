# tts_daemon — launchd service

## Install

```sh
cp launchd/com.liino.qwen-tts-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.liino.qwen-tts-daemon.plist
```

## Stop

```sh
launchctl unload ~/Library/LaunchAgents/com.liino.qwen-tts-daemon.plist
```

- Socket: `/tmp/qwen_tts_daemon.sock` (Unix domain only)
- Logs: `/tmp/qwen_tts_daemon.log` / `/tmp/qwen_tts_daemon.err.log`
- Cache: `~/.cache/qwen_tts/`
- RunAtLoad + KeepAlive อยู่แล้ว — daemon จะถูก restart อัตโนมัติถ้า crash
