# Files and assets

One reusable `Asset` model for every file in the system: uploads, generated files,
fetched remote files, and internal system files. Features attach assets through
join models; no feature creates its own file model. The storage backend, delivery
mode, URL lifetimes, and size limits come from the profile.

## Contents

1. The Asset model
2. Attaching assets to other models
3. Purposes and visibility
4. Upload validation by content
5. Delivery: signed URLs
6. Deletion
7. The upload endpoint
8. Encrypted internal content
9. Recipes: attach files to a model, serve a new kind of file

---

## 1. The Asset model

```python
class Asset(PublicModel):
    """A stored file owned by an organization.

    Owner: files.
    Tenant scope: organization (optionally project).
    Lifecycle: processing -> ready | failed | quarantined; any -> deleted (tombstone).
    Invariants:
        - project, when set, belongs to organization (checked in save()).
        - A producer writes each output index once (files_asset_producer_index_uniq).
    Data classification: internal metadata; content inherits the uploader's class.
    Append-only: no.
    Events: file.ready, file.deleted.
    """

    class Kind(models.TextChoices):
        DOCUMENT = "document", _("Document")
        IMAGE = "image", _("Image")
        AUDIO = "audio", _("Audio")
        VIDEO = "video", _("Video")

    class Source(models.TextChoices):
        UPLOAD = "upload", _("Upload")
        REMOTE = "remote", _("Remote")
        GENERATED = "generated", _("Generated")

    class Status(models.TextChoices):
        PROCESSING = "processing", _("Processing")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")
        QUARANTINED = "quarantined", _("Quarantined")
        DELETED = "deleted", _("Deleted")

    organization = models.ForeignKey("access.Organization", on_delete=models.CASCADE, related_name="assets")
    project = models.ForeignKey("access.Project", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="assets")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="created_assets")

    file = models.FileField(upload_to=asset_upload_to)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.UPLOAD)
    purpose = models.CharField(max_length=40, default="user_data")
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=150, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_sha256 = models.CharField(max_length=64, blank=True, default="", editable=False)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)

    metadata = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True, default="")
```

- Indexes: `(organization, status)`, `(organization, kind, status)`, a partial
  `(organization, -created_at, -id)` excluding deleted rows, and `(content_sha256)`.
- `asset_upload_to` builds `assets/<organization_id>/<first 2 hex of id>/<id><ext>`.
  The client's file name never appears in the storage path.
- `quarantined` is the state a malware or content scanner puts files into.
- Generated files carry a producer reference and index, with a conditional unique
  constraint, so a retried producer cannot create duplicates.

## 2. Attaching assets to other models

```python
class OrderAttachment(PublicModel):
    """<contract>"""
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="attachments")
    asset = models.ForeignKey("files.Asset", on_delete=models.RESTRICT, related_name="order_attachments")
    position = models.PositiveSmallIntegerField(default=0)
```

- One asset may be referenced by many owners through join rows (`RESTRICT`, with an
  explicit `position`).
- `resolve_assets(principal, ids)` returns **all** requested `ready` assets in the
  caller's order, or raises; never a partial list. It enforces the per-request count
  and total-size caps.

## 3. Purposes and visibility

`files/services/asset_purposes.py`:
- `PUBLIC_PURPOSES`: set by callers and visible to them;
- `GENERATED_PURPOSES`: written by the system for the caller and visible to them;
- `INTERNAL_PURPOSES`: platform-owned, never visible to callers.

`visible_assets(principal, *, include_internal=False)` is the **only** sanctioned
queryset builder for caller-reachable assets. It scopes by tenant and excludes
internal purposes. If purposes are stored in JSON, keep rows with no purpose key
explicitly: SQL `NULL` makes a plain `.exclude(...__in=...)` drop them.

## 4. Upload validation by content

`inspect_upload(upload) -> AssetUploadMetadata` is pure inspection; storing is a
separate function.
- The extension is allowlisted, and the declared MIME type must match it. A generic
  `application/octet-stream` is replaced by the canonical type.
- **Sniff the real content**: PDF header, OLE header, OOXML zip structure
  (`[Content_Types].xml` plus the expected part prefix), UTF-8 text.
- **Archives**: cap the entry count and total uncompressed size, and reject
  encrypted entries.
- **Images**: open with Pillow, call `verify()`, and enforce maximum width, height,
  and pixel area (decompression bombs).
- Read in chunks while computing SHA-256. Never read an unbounded upload into memory.
- Per-kind size limits come from settings.

## 5. Delivery: signed URLs

```python
FILES_URL_SALT = "files.asset-delivery.v1"
CLIENT_AUDIENCE_SALT = f"{FILES_URL_SALT}:client"      # longer-lived, for our clients
PARTNER_AUDIENCE_SALT = f"{FILES_URL_SALT}:partner"    # short-lived, for third parties


def _token(asset_id: uuid.UUID, *, salt: str) -> str:
    # No explicit key: Django signs with SECRET_KEY and verifies with
    # SECRET_KEY_FALLBACKS too, so a key rotation does not break live links.
    return signing.dumps({"asset_id": str(asset_id)}, salt=salt, compress=True)


def validate_delivery_token(token: str, *, asset_id: uuid.UUID) -> bool:
    for salt, max_age in ((CLIENT_AUDIENCE_SALT, settings.FILES_CLIENT_URL_TTL_SECONDS),
                          (PARTNER_AUDIENCE_SALT, settings.FILES_PARTNER_URL_TTL_SECONDS)):
        try:
            if signing.loads(token, salt=salt, max_age=max_age) == {"asset_id": str(asset_id)}:
                return True
        except signing.BadSignature:        # includes SignatureExpired
            continue
    return False
```

- **Audience-separated salts**, each with its own lifetime. A token for one audience
  cannot be replayed as the other.
- Responses include `url` and `expires_in`, so clients refresh in time.
- **Delivery mode** is a setting:
  - `proxy`: the app streams the file through a content view;
  - `storage`: the app redirects to a short-lived presigned object-storage URL.

  Calling code never changes when the mode changes.
- The **content view**:
  - is `AllowAny` with `authentication_classes = []`, authorized by the token alone,
    and throttled per token and globally;
  - returns 404 for a bad or expired token, and serves only `ready` assets;
  - streams the file with the stored `Content-Type`,
    `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` for
    non-images, and `Cache-Control: private` with a max-age no longer than the token.

## 6. Deletion

```python
def delete_owned_asset(*, principal: RequestPrincipal, asset_id: uuid.UUID) -> None:
    """Tombstone an asset and delete its blob after commit.

    Raises `Asset.DoesNotExist` (404) for a missing, foreign, or deleted asset.
    Emits `file.deleted` and writes a `file.delete` audit event.
    """
    with transaction.atomic():
        asset = visible_assets(principal).select_for_update().get(id=asset_id)
        require(principal, action="file.delete", resource=asset)
        if asset.status == Asset.Status.DELETED:
            raise Asset.DoesNotExist
        storage, storage_name = asset.file.storage, asset.file.name
        Asset.objects.filter(id=asset.id).update(
            status=Asset.Status.DELETED, file="", original_name="", mime_type="",
            size_bytes=0, content_sha256="", width=None, height=None, metadata={},
            updated_at=timezone.now(),
        )
        audit.record(principal=principal, action="file.delete", target=asset)
        emit(AssetDeleted.from_principal(principal, subject_id=asset.id,
                                         organization_id=asset.organization_id))

        def delete_blob() -> None:
            if storage_name and not Asset.objects.filter(file=storage_name).exists():
                storage.delete(storage_name)

        transaction.on_commit(delete_blob, robust=True)
```

- The row becomes a tombstone. The blob is deleted **after commit**, and only if no
  other row references it.
- When blob deletion must be guaranteed, record a durable cleanup job instead
  (`events-and-jobs.md` §10).
- Join rows with `RESTRICT` are handled first: a SYNC handler of `file.deleted`
  detaches them, or the delete is refused with a clear error.

## 7. The upload endpoint

- Only `POST /files` accepts `multipart/form-data`, with the fields `file` and
  `purpose`. It returns the file object, including `url` and `expires_in`.
- Other resources reference uploaded files by `file_ids`. JSON never carries base64
  files.
- It is throttled, and its size limits come from settings.

## 8. Encrypted internal content

For platform-owned sensitive blobs: encrypt with `MultiFernet`, using keys derived
from `SECRET_KEY` and every `SECRET_KEY_FALLBACKS` entry (through HKDF or PBKDF2
with a dedicated salt setting). Decryption survives a key rotation, and new writes
use the current key.

## 9. Recipes

### 9.1 Attach files to a model

1. Add a join model (§2) with a contract docstring, `RESTRICT` on the asset, and a
   `position`.
2. The input serializer accepts `file_ids`. The service calls `resolve_assets`,
   which enforces all-or-nothing and the caps.
3. The output includes each file's `url` and `expires_in`.
4. Handle `file.deleted` (detach, or refuse the delete).
5. Tests:
   - foreign and unready IDs rejected;
   - the caps;
   - ordering preserved;
   - deletion behavior.

### 9.2 Serve a new kind of file

1. Add the extension and MIME types to the allowlist, plus content sniffing for the
   format.
2. Add a size limit setting.
3. Tests:
   - a valid file;
   - a renamed file of another type is rejected;
   - an oversized or bomb-like file is rejected.
