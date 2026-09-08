# Jarvis → Caleb Reverse Sync

Once Jarvis has approved, named and archived a title, the ServerSync/Edge pull path may populate Caleb's cache.

```text
Jarvis authoritative library
        |
        v
ServerSync discovery
        |
        v
caleb-edge-pull
        |
        +--> capacity reserve okay -> download/resume -> local playable file
        |
        +--> reserve would be violated -> stop; title remains safe on Jarvis
```

The reverse path is convenience/locality, not preservation authority.
