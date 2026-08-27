import os
import uuid
from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'xlsx', 'xls', 'doc', 'docx', 'eml', 'msg'}
ALLOWED_MIMES = {
    'application/pdf', 'image/png', 'image/jpeg', 'image/gif',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'message/rfc822', 'application/vnd.ms-outlook'
}


def allowed_file(file):
    """Validate file extension and optionally MIME type. Returns (is_valid, error_msg)."""
    filename = secure_filename(file.filename)
    if '.' not in filename:
        return False, 'File must have an extension.'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f'File type .{ext} is not allowed.'
    try:
        import magic
        header = file.read(2048)
        file.seek(0)
        mime = magic.from_buffer(header, mime=True)
        if mime not in ALLOWED_MIMES:
            return False, f'File content type {mime} is not permitted.'
    except (ImportError, OSError) as e:
        # ImportError: python-magic package not installed.
        # OSError: package installed but the underlying libmagic1 shared
        # library isn't present on the system (e.g. App Service without
        # apt access) — python-magic raises this at import/use time, not
        # ImportError, so it must be caught here too or uploads 500.
        current_app.logger.warning("python-magic unavailable (%s); falling back to extension-only validation.", e)
    return True, None


def _get_blob_service_client():
    """
    Build a BlobServiceClient using Managed Identity, matching the same
    auth pattern already used for Azure SQL (no account keys/connection
    strings — those are long-lived secrets with full account access and
    don't tie back to an identity for auditing).

    Requires AZURE_STORAGE_ACCOUNT_URL (e.g.
    https://jeef01npeuwdvaccio01.blob.core.windows.net) and a Managed
    Identity with Storage Blob Data Contributor on the storage account.
    """
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    account_url = current_app.config.get('AZURE_STORAGE_ACCOUNT_URL', '')
    if not account_url:
        return None
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=credential)


def save_file(file):
    """
    Save uploaded file.
    - If AZURE_STORAGE_ACCOUNT_URL is set: uploads to Azure Blob Storage
      using the App Service's Managed Identity.
    - Otherwise: saves to local filesystem (dev only).
    Returns (original_filename, unique_name).
    """
    if not file or not file.filename:
        return None, None

    original_filename = secure_filename(file.filename)
    unique_name = f'{uuid.uuid4().hex}_{original_filename}'

    account_url = current_app.config.get('AZURE_STORAGE_ACCOUNT_URL', '')
    container = current_app.config.get('AZURE_STORAGE_CONTAINER', 'accio-uploads')

    if account_url:
        try:
            blob_service = _get_blob_service_client()
            blob_client = blob_service.get_blob_client(container=container, blob=unique_name)
            file.seek(0)
            blob_client.upload_blob(file.read(), overwrite=True)
            current_app.logger.info(f'Uploaded blob: {unique_name} to container: {container}')
            return original_filename, unique_name
        except Exception as e:
            current_app.logger.error(f'Azure Blob upload failed: {e}')
            raise RuntimeError(f'File upload to Azure Blob failed: {e}')

    # Local filesystem fallback (development only)
    upload_folder = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_folder, unique_name)
    file.save(filepath)
    return original_filename, unique_name


def get_file_path(filename):
    """Get full local path for a stored file (dev fallback only)."""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], filename)


def get_download_url(blob_name, original_name=None):
    """
    Returns a short-lived SAS URL for Azure Blob (production),
    or None if running locally.

    Uses a user delegation SAS — signed by the Managed Identity's
    delegated permissions rather than an account key, since Managed
    Identity has no account key to hand over. Requires the Managed
    Identity to have Storage Blob Data Contributor (or similar) on the
    storage account.
    """
    account_url = current_app.config.get('AZURE_STORAGE_ACCOUNT_URL', '')
    container = current_app.config.get('AZURE_STORAGE_CONTAINER', 'accio-uploads')

    if not account_url:
        return None

    try:
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        from datetime import datetime, timezone, timedelta

        client = _get_blob_service_client()
        account_name = client.account_name

        delegation_key_start = datetime.now(timezone.utc)
        delegation_key_expiry = delegation_key_start + timedelta(hours=1)
        user_delegation_key = client.get_user_delegation_key(
            key_start_time=delegation_key_start,
            key_expiry_time=delegation_key_expiry,
        )

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=delegation_key_expiry,
            content_disposition=f'attachment; filename="{original_name or blob_name}"'
        )
        return f'https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}'
    except Exception as e:
        current_app.logger.error(f'Failed to generate SAS URL: {e}')
        return None
