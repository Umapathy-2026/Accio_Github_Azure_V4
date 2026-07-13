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
    except ImportError:
        pass  # fallback to extension-only validation if python-magic not available
    return True, None


def save_file(file):
    """
    Save uploaded file.
    - If AZURE_STORAGE_CONNECTION_STRING is set: uploads to Azure Blob Storage.
    - Otherwise: saves to local filesystem (dev only).
    Returns (original_filename, unique_name).
    """
    if not file or not file.filename:
        return None, None

    original_filename = secure_filename(file.filename)
    unique_name = f'{uuid.uuid4().hex}_{original_filename}'

    conn_str = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING', '')
    container = current_app.config.get('AZURE_STORAGE_CONTAINER', 'accio-uploads')

    if conn_str:
        try:
            from azure.storage.blob import BlobServiceClient
            blob_service = BlobServiceClient.from_connection_string(conn_str)
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
    """
    conn_str = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING', '')
    container = current_app.config.get('AZURE_STORAGE_CONTAINER', 'accio-uploads')

    if not conn_str:
        return None

    try:
        from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
        from datetime import datetime, timezone, timedelta

        client = BlobServiceClient.from_connection_string(conn_str)
        account_name = client.account_name
        account_key = client.credential.account_key

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
            content_disposition=f'attachment; filename="{original_name or blob_name}"'
        )
        return f'https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}'
    except Exception as e:
        current_app.logger.error(f'Failed to generate SAS URL: {e}')
        return None