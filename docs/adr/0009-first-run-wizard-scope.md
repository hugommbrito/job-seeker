# 0009. What the first-run wizard collects in Phase 1

2026-11-24. Accepted. Narrows the Phase 1 item "first-run wizard: profile, tracks, hard filters,
home location, channels" in the implementation plan, section 7, and defers part of section 5.5.

## Context

Section 5.5 sets the home location "either by dropping a map pin or by geocoding an address
once". A map needs a tile server and an address needs a geocoder: either one is a third party
that learns roughly where the user lives, and decision 25 chose the offline commute heuristic so
that the home location never leaves the server. Nothing in Phase 1 uses the location; the
commute components arrive in Phase 2. The ranking weights (`profiles.soft`) have no consumer
before Phase 2 either.

## Decision

- The wizard has five steps: timezone, tracks, hard filters, home, notifications. Each saves on
  its own, every step is optional, and "Skip the rest" marks setup as done. It opens once, when
  a member who has not finished it lands on the app; afterwards the same sections are on the
  settings page.
- Home is a label and coordinates, typed or taken from the browser's own geolocation, which
  involves no service of this app. The map pin and the one-time geocoding are built with the
  commute components in Phase 2, where the choice of tile and geocoding source can be made
  against the rule that the location stays on the server.
- `hard` and `notify` are validated by Pydantic on every read (`apps.profiles.settings`); a row
  that no longer validates is logged by id and read as the defaults. `soft` is added in Phase 2
  with the scorer that reads it, instead of storing weights nothing uses.
- The notification step covers reminders and quiet hours. Linking a phone channel lives on the
  settings page, where it can wait for the bot to answer.

## Consequences

- Phase 2 adds a `soft` field and the map, and must keep existing `hard` rows valid.
- Until then the home location is only as precise as what the user types or the browser shares.
