# SPDX-License-Identifier: EUPL-1.2
"""Erzeugt das leere Vorlagen-ZIP (ein Kapitel, eine Seite, ein Absatz)."""
from __future__ import annotations

import io
import time
import zipfile

from ._skelett_daten import DATEI_REIHENFOLGE, DATEIEN, VERZEICHNISSE

ATTR_VERZEICHNIS = 0o10177600000
ATTR_DATEI = 0o20176000000


def vorlage_zip(wurzel: str, quell_id: str, installations_url: str,
                zeitpunkt: float | None = None) -> bytes:
    """Liefert die Vorlage als ZIP-Bytes mit dem Hauptordner ``wurzel``."""
    stempel = time.localtime(zeitpunkt if zeitpunkt is not None else time.time())[:6]
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as ziel:
        for name in VERZEICHNISSE:
            info = zipfile.ZipInfo(f"{wurzel}/{name}", date_time=stempel)
            info.external_attr = ATTR_VERZEICHNIS
            info.create_system = 3
            ziel.writestr(info, b"")
        for name in DATEI_REIHENFOLGE:
            text = DATEIEN[name].replace("{{URL}}", installations_url).replace("{{MID}}", quell_id)
            info = zipfile.ZipInfo(f"{wurzel}/{name}", date_time=stempel)
            info.external_attr = ATTR_DATEI
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            ziel.writestr(info, text.encode("utf-8"))
    return puffer.getvalue()
