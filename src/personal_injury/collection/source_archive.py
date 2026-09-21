"""Content-addressed original statistical documents; independent of web/collector deps."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


class ArchiveStore:
    def __init__(self, root: str | Path | None = None):
        default = Path.cwd() / "data" / "source_archive"
        self.root = Path(root or os.getenv("STATISTICAL_ARCHIVE_DIR") or default).resolve()

    def _path(self, digest: str) -> Path | None:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        path = self.root / digest[:2] / (digest + ".bin")
        if not path.resolve().is_relative_to(self.root):
            return None
        return path

    def resolve(self, digest: str) -> Path | None:
        """Only return an intact, bounded blob under the configured archive root."""
        path = self._path(digest)
        if path is None or not path.is_file():
            return None
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            return None
        checksum = hashlib.sha256()
        with path.open("rb") as source:
            total = 0
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    return None
                checksum.update(chunk)
        return path if checksum.hexdigest() == digest else None

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp") as output:
                temporary = Path(output.name)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save(
        self, content: bytes, *, source_url: str, content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, bytes) or len(content) > MAX_ARCHIVE_BYTES:
            raise ValueError("原始文档必须是20 MiB以内的字节内容")
        digest = hashlib.sha256(content).hexdigest()
        path = self._path(digest)
        if path is None:
            raise ValueError("原文归档路径越界")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if self.resolve(digest) is None:
                raise ValueError("现有原文归档哈希不一致，拒绝覆盖")
        else:
            self._write(path, content)
        description = {
            "content_sha256": digest, "source_url": source_url,
            "content_type": content_type, "metadata": metadata or {},
        }
        manifest = json.dumps(description, ensure_ascii=False, sort_keys=True).encode("utf-8")
        manifest_digest = hashlib.sha256(manifest).hexdigest()
        manifest_path = path.parent / f"{digest}.{manifest_digest}.json"
        if not manifest_path.resolve().is_relative_to(self.root):
            raise ValueError("原文归档元数据路径越界")
        if not manifest_path.exists():
            self._write(manifest_path, manifest)
        return {
            "content_sha256": digest, "archive_sha256": digest,
            "content_type": content_type,
            "archive_path": path.relative_to(self.root).as_posix(),
            "archive_metadata_path": manifest_path.relative_to(self.root).as_posix(),
        }
