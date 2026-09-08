# Library Layout

Jellyfin's media namespace is exposed through `/media` inside the container, backed by `/srv/media` on the host.

The production Shows library was normalized to the canonical external-media path so duplicate local/external library roots are not treated as separate copies.

The physical cache and the visible catalog are conceptually separate. The long-term user experience should allow a shared item to be visible even when its only physical copy is on Jarvis.
