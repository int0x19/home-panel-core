# Shared Sensor Draft Transactions

Core 0.1.2 extends the existing `runtime-draft.mjs`, not the JSON schema or the
ESP32 capability inventory. The same asset remains the source for Linux and
HA consumers. Pure Python/C++ validation and shared LVGL remain authoritative.

`put_sensor` uses `room`, `target`, a new `id` or existing `previous` placement,
and `settings` with `entity` (`sensor.*`), `name` and optional `unit`,
`device_class`, `group`. `group_name` optionally sets the target group's shared
title; an empty string removes the title, not the grouping. Omit the group for
a standalone card. New group IDs use the ordinary ASCII identifier contract.
`move_sensor` changes placement order; `delete_sensor` removes a placement and
only its now-unused group definition. Moves across rooms preserve placement
identity, copy the needed group definition and reject target ID/entity clashes.
The same source may appear independently in different rooms.

Every edit is cloned and published only on success. Unsupported fields or
widget families stay opaque; unrelated room renames preserve them. Sensor edits
require both `widget.sensor` in features and `sensor` in the negotiated widget
inventory; grouping additionally requires `sensor-groups.v1`. Sensor placement
on Actions-only pages is rejected. No new profile is inferred from HA states.

The logical fit guard coalesces nonadjacent group members at their first
occurrence, limits named groups to two columns and packs adjacent action tiles
without reordering them. It retains the existing fixed 320x480/no-scroll
geometry and dense-group minimum width. Capacity failures retain the old
document; they do not shrink fonts or silently paginate a room. Existing
action-only pagination remains unchanged. Unique entity bindings are counted
against the negotiated source limit when all room content is understood.

The ten Node-driven test cases compare mixed-row heights with the existing
Python planner and cover atomic failures, opaque data, UTF-8, group-title
changes, prototype-like IDs, feature/inventory gates and repeated bindings.
Core's 49-test suite, including loopback HTTP, passes. This is source-level
logical acceptance, not installed HA/ESP32 rendering or deployment acceptance.
