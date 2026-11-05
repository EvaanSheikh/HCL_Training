import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.dataset_validation import validate_dataset
from app.security import MAX_DATASET_SIZE_BYTES, MAX_MULTIPART_FIELD_SIZE_BYTES
from app.auth import Principal, get_user_id, require_principal
from app.storage.database import register_dataset, save_dataset_metadata, owns_dataset, get_connection


router = APIRouter()

# Project root: HCL_Training/
BASE_DIR = Path(__file__).resolve().parents[2]

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json"}
MAX_FILE_SIZE = MAX_DATASET_SIZE_BYTES
CHUNK_SIZE = 1024 * 1024  # 1 MB


class UploadedFileTooLarge(MultiPartException):
    pass


class BoundedUploadParser(MultiPartParser):
    """Apply a per-file byte cap before Starlette writes chunks to its spool."""

    def __init__(self, headers, stream, *, max_file_size: int):
        super().__init__(headers, stream, max_files=1, max_fields=0,
                         max_part_size=MAX_MULTIPART_FIELD_SIZE_BYTES)
        self.max_file_size = max_file_size
        self.current_file_size = 0

    def on_part_begin(self) -> None:
        self.current_file_size = 0
        super().on_part_begin()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.current_file_size += end - start
            if self.current_file_size > self.max_file_size:
                raise UploadedFileTooLarge("Uploaded file exceeds the configured size limit.")
        super().on_part_data(data, start, end)


async def _save_uploaded_file(file: UploadFile, principal: Principal):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Allowed formats: CSV, XLSX, JSON."
            ),
        )

    dataset_id = str(uuid4())
    destination = UPLOAD_DIR / f"{dataset_id}{extension}"

    total_size = 0
    created = False

    try:
        # Exclusive creation prevents replacing an existing file if the
        # generated destination unexpectedly collides or is pre-created.
        with destination.open("xb") as output_file:
            created = True
            # Apply restrictive permissions immediately after creation
            # so that no intermediate window allows world-read.
            # Windows uses directory ACLs; chmod is a no-op there.
            if os.name != "nt":
                os.chmod(destination, 0o600)
            while True:
                chunk = await file.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 100 MB size limit.",
                    )

                output_file.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty.",
            )

        # Validate actual dataset contents.
        validation = validate_dataset(str(destination))
        owner_id = get_user_id(principal)
        register_dataset(dataset_id, owner_id, extension)
        save_dataset_metadata(
            dataset_id,
            file.filename,
            total_size,
            validation.get("rows"),
            validation.get("columns"),
            validation,
        )

    except HTTPException:
        if created:
            destination.unlink(missing_ok=True)
        raise

    except (FileNotFoundError, ValueError) as exc:
        if created:
            destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="Dataset is invalid or exceeds configured limits.",
        ) from exc

    except Exception as exc:
        if created:
            destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Dataset upload failed.",
        ) from exc

    finally:
        await file.close()

    return {
        # Expose only the opaque ID, never the server filesystem path.
        "dataset_id": dataset_id,
        "filename": file.filename,
        "size_bytes": total_size,
        "extension": extension,
        "validation": validation,
    }


@router.post("/upload")
async def upload_dataset(request: Request, principal: Principal = Depends(require_principal)):
    parser = BoundedUploadParser(request.headers, request.stream(), max_file_size=MAX_FILE_SIZE)
    try:
        form = await parser.parse()
    except UploadedFileTooLarge:
        raise HTTPException(status_code=413, detail="File exceeds the 100 MB size limit.") from None
    except MultiPartException:
        raise HTTPException(status_code=400, detail="Invalid multipart upload.") from None

    try:
        files = form.multi_items()
        if len(files) != 1 or files[0][0] != "file" or not isinstance(files[0][1], UploadFile):
            raise HTTPException(status_code=400, detail="Provide exactly one file upload.")
        return await _save_uploaded_file(files[0][1], principal)
    finally:
        await form.close()


@router.post("/datasets/replace/{dataset_id}")
async def replace_dataset(
    dataset_id: str,
    request: Request,
    principal: Principal = Depends(require_principal),
):
    owner_id = get_user_id(principal)
    if not owns_dataset(dataset_id, owner_id):
        raise HTTPException(status_code=404, detail="Dataset not found.")

    parser = BoundedUploadParser(request.headers, request.stream(), max_file_size=MAX_FILE_SIZE)
    try:
        form = await parser.parse()
    except UploadedFileTooLarge:
        raise HTTPException(status_code=413, detail="File exceeds the 100 MB size limit.") from None
    except MultiPartException:
        raise HTTPException(status_code=400, detail="Invalid multipart upload.") from None

    try:
        files = form.multi_items()
        if len(files) != 1 or files[0][0] != "file" or not isinstance(files[0][1], UploadFile):
            raise HTTPException(status_code=400, detail="Provide exactly one file upload.")
        file = files[0][1]

        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required.")

        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file type. Allowed formats: CSV, XLSX, JSON.")

        temp_dest = UPLOAD_DIR / f"{dataset_id}_temp{extension}"
        total_size = 0
        try:
            with temp_dest.open("wb") as out:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(status_code=413, detail="File exceeds the 100 MB size limit.")
                    out.write(chunk)

            if total_size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")

            validation = validate_dataset(str(temp_dest))

            with get_connection() as conn:
                old_row = conn.execute("SELECT extension FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
                if old_row and old_row["extension"] != extension:
                    old_file = UPLOAD_DIR / f"{dataset_id}{old_row['extension']}"
                    old_file.unlink(missing_ok=True)
                conn.execute("UPDATE datasets SET extension=? WHERE dataset_id=?", (extension, dataset_id))
                conn.commit()

            final_dest = UPLOAD_DIR / f"{dataset_id}{extension}"
            if final_dest.exists():
                final_dest.unlink()
            temp_dest.rename(final_dest)

            save_dataset_metadata(
                dataset_id,
                file.filename,
                total_size,
                validation.get("rows"),
                validation.get("columns"),
                validation,
            )

            return {
                "dataset_id": dataset_id,
                "filename": file.filename,
                "size_bytes": total_size,
                "extension": extension,
                "validation": validation,
            }
        except Exception:
            temp_dest.unlink(missing_ok=True)
            raise
    finally:
        await form.close()
