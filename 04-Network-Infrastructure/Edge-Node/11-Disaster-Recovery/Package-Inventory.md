# Package Inventory

The exact dpkg inventory and manually installed package list from the 2026-09-07 working snapshot are stored under:

```text
12-Reference-Snapshot/software/packages-all.txt
12-Reference-Snapshot/software/packages-manual.txt
12-Reference-Snapshot/software/software-state.txt
```

Use these as a reconstruction reference rather than blindly reinstalling every dependency. Start with role-required packages and verify each service as it is restored.
