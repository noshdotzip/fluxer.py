from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional


@dataclass
class File:
    fp: BinaryIO
    filename: str
    content_type: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "File":
        p = Path(path)
        fp = p.open("rb")
        return cls(fp=fp, filename=filename or p.name, content_type=content_type, description=description)

    def to_form(self, form, index: int) -> None:
        field_name = f"files[{index}]"
        form.add_field(
            field_name,
            self.fp,
            filename=self.filename,
            content_type=self.content_type,
        )
