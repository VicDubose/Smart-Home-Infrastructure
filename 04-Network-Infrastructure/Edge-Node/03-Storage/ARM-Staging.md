# ARM / Raw Staging

The staging filesystem is a 50 GiB ext4 loop image mounted at `/srv/staging`.

Persistent structure:

```text
/srv/staging/
├── Raw_Rips/
│   ├── DVD/
│   └── Bluray/
├── Transfer_Queue/
├── Confirmed/
└── Failed/
```

The staging area is deliberately transient. It exists to safely move raw media toward Jarvis, not to become another permanent library.

`caleb-staging-flush.timer` checks hourly. The deployed confirmed-media cleanup policy deletes files in `Confirmed/` after 72 hours.
