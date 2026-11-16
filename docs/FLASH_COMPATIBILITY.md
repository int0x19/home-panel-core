# Flash Configuration Storage Compatibility

Core 0.1.1 accepts the deployed HTTP v1 flash profile in addition to the legacy
SD profile. `storage: flash-nvs` must explicitly advertise
`flash-maintenance.v1` and carry a boolean `storage_ready`. Loaded sources may
be `builtin`, `flash-confirmed`, `flash-previous` or `flash-trial`. An unknown
storage type or an inconsistent/missing profile is rejected.

`sd_ready` remains the actual SD flag. `RuntimeStatus.storage_ready` reports
configuration storage availability and gates exports, so flash does not require
a card. Legacy status without `storage` retains its SD-based meaning. Explicit
`sd-files` readiness must agree with `sd_ready`. Storage kind/readiness changes
during a read/check transaction invalidate the result.

The flash profile also carries `storage_generation` as a canonical unsigned
64-bit decimal string. Forward it unchanged in `X-Panel-Storage-Generation`
for export/validate POSTs; never convert it through a JavaScript number. Missing,
malformed and out-of-range values are rejected before a POST. A generation
change during a transaction invalidates its result as well.

No upload, recovery, apply or household action is added. Existing factory-ID,
session, capability, byte-limit, filename and SHA-256 guards remain mandatory.
Pairing still does not mean managed deployment is available. Status/capabilities
were read on the panel to diagnose the previous `Invalid loaded source` error;
this change requires no firmware build or OTA.
