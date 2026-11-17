# Flash Write-Base Preconditions

The unpublished 0.1.2 development version reads the optional status feature
`write-base.v1`. Its `write_base_sha256` field is either a lowercase 64-character
SHA-256 token or null when the device cannot form a healthy snapshot. A missing
feature means unsupported, never an inferred permission to write. Legacy SD
and older flash status remain readable with a null core property.

The firmware alone computes this opaque token from builtin bytes and the full
logical flash metadata state. It is independent of C struct padding, copy order
and HTTP boot nonce. Generation, high-water revision, confirmed/previous/staged
references and pending-trial identity are included. It is not the digest of the
proposed draft, a credential, an owner ID or an authentication mechanism.

The flash HTTP maintenance writer now requires `X-Panel-Write-Base` for Upload,
Apply, Discard and recovery-candidate operations. It also retains the existing
identity/authentication, session, operation revision, flash generation, target
digest and boot-health checks. The main-loop NVS transaction recomputes the
base under the same exclusive lease as its fresh audit, before opening write
access. Multi-turn preparation may not substitute a newer base after decoding.
The storage-v1 record format is unchanged; SDK boot/confirmation requests do
not acquire browser preconditions.

Future HA writers must retain the baseline associated with the imported draft,
not fetch a new token and silently bless an older draft. After an acknowledged
Send, Apply needs an explicitly verified new candidate/base. Missing/malformed
headers are bad requests, changed/unavailable bases are conflicts and hash/I/O
failures are unavailable outcomes. Read fresh status; never replay a write.

This core still exposes no upload/Apply methods. Read/check operations send no
write-base header. They compare the typed token before/after the transaction,
including changes at the same numeric generation, and require a fresh explicit
status after conflict. HA can keep that validated snapshot on its backend;
frontend edits/checkpoints alone confer neither an owner nor write authority.

Source acceptance passes 52 tests, including malformed/legacy token handling
and a read/check race without automatic replay. Consumer acceptance and the
firmware boundary are separate gates. No package is published and no physical
configuration is changed by these source changes.

Next implement persistent ownership/scoped authentication and explicit local
handover/recovery. Only then add guarded HA Send/Apply and device activation
acceptance. Write-base is concurrency protection, not ownership enforcement.

Consumer checkpoint, 2026-11-17: all 52 installed-wheel tests and 214 HA tests
pass from functional source `d414a7f2e7fb283d1c66c84bc1521da7cb345ad9`. The
firmware passes 80 scoped flash HTTP/NVS/client cases (two optional skips),
28 compatibility/decode/codegen checks, a separate flash ASan/UBSan run and
two loopback browser workflows. All 21 wheel files match the locked source.
No full firmware sweep, physical OTA or release is implied. Documentation-only
updates do not change the tested functional pin.
