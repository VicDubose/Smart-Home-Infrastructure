# Storage Policies

## Edge cache policy

Caleb is allowed to be storage-limited. Jarvis is the preservation tier.

```text
Enough Caleb space?  YES -> keep/sync local playable copy
                     NO  -> preserve on Jarvis; Caleb can sync later
```

## Raw staging policy

1. Raw disc content is written to staging.
2. Transfer toward Jarvis must complete and be confirmed before eligible raw data is removed.
3. Confirmed transfers are currently eligible for automatic deletion after **72 hours**.
4. The broader design note allows a raw recovery ceiling of up to **7 days** if a separate unconfirmed/recovery tier is implemented later.

Never delete the only known good copy merely to make room on the Edge node.
