"""Load the ETIM 10.0 model from the vendored archive.

The archive ships UTF-16 encoded, `;`-delimited CSVs. Parsing all eight files takes
a couple of seconds, so the result is cached per-path for the life of the process.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from skutruth.contracts import EtimFeatureType

from .model import EtimAllowedValue, EtimClass, EtimFeature, EtimModel

#: Repo-relative location of the vendored release. See data/etim/ATTRIBUTION.md.
DEFAULT_ARCHIVE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "etim"
    / "ETIM-10.0-ALL-SECTORS-CSV-METRIC-EI-2024-12-05.zip"
)
DEFAULT_RELEASE = "ETIM 10.0"

# The archive is UTF-16; a BOM-tolerant decode keeps the first header cell clean.
_ENCODING = "utf-16"
_DELIMITER = ";"


def _read_rows(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = zf.read(name).decode(_ENCODING).lstrip("﻿")
    return list(csv.DictReader(io.StringIO(text), delimiter=_DELIMITER))


def _int(raw: str | None, default: int = 0) -> int:
    try:
        return int((raw or "").strip())
    except ValueError:
        return default


@lru_cache(maxsize=4)
def load_etim(archive: Path | None = None, release: str = DEFAULT_RELEASE) -> EtimModel:
    """Parse the ETIM archive into an `EtimModel`. Cached per archive path."""
    path = Path(archive) if archive is not None else DEFAULT_ARCHIVE
    if not path.exists():
        raise FileNotFoundError(
            f"ETIM archive not found at {path}. It is committed to the repository; "
            "see data/etim/ATTRIBUTION.md."
        )

    with zipfile.ZipFile(path) as zf:
        groups = {r["ARTGROUPID"]: r["GROUPDESC"] for r in _read_rows(zf, "ETIMARTGROUP.csv")}
        units = {r["UNITOFMEASID"]: r["UNITDESC"] for r in _read_rows(zf, "ETIMUNIT.csv")}
        feature_rows = _read_rows(zf, "ETIMFEATURE.csv")
        feature_names = {r["FEATUREID"]: r["FEATUREDESC"] for r in feature_rows}
        value_names = {r["VALUEID"]: r["VALUEDESC"] for r in _read_rows(zf, "ETIMVALUE.csv")}
        class_rows = _read_rows(zf, "ETIMARTCLASS.csv")
        feature_map = _read_rows(zf, "ETIMARTCLASSFEATUREMAP.csv")
        value_map = _read_rows(zf, "ETIMARTCLASSFEATUREVALUEMAP.csv")
        synonym_rows = _read_rows(zf, "ETIMARTCLASSSYNONYMMAP.csv")

    # Allowed values, grouped by the class-feature join key.
    values_by_cf: dict[str, list[EtimAllowedValue]] = defaultdict(list)
    for row in value_map:
        vid = row["VALUEID"]
        text = value_names.get(vid)
        if text is None:
            continue  # value referenced but absent from the dictionary; skip rather than invent
        values_by_cf[row["ARTCLASSFEATURENR"]].append(
            EtimAllowedValue(value_id=vid, text=text, sort_nr=_int(row.get("SORTNR")))
        )
    for members in values_by_cf.values():
        members.sort(key=lambda v: (v.sort_nr, v.text))

    # Features, grouped by class.
    features_by_class: dict[str, list[EtimFeature]] = defaultdict(list)
    for row in feature_map:
        fid = row["FEATUREID"]
        name = feature_names.get(fid)
        if name is None:
            continue
        try:
            ftype = EtimFeatureType(row["FEATURETYPE"].strip())
        except ValueError:
            continue  # unknown type code: better to omit than to guess a type
        cf_nr = row["ARTCLASSFEATURENR"]
        unit_id = (row.get("UNITOFMEASID") or "").strip()
        features_by_class[row["ARTCLASSID"]].append(
            EtimFeature(
                feature_id=fid,
                name=name,
                feature_type=ftype,
                unit=units.get(unit_id) if unit_id else None,
                sort_nr=_int(row.get("SORTNR")),
                class_feature_nr=cf_nr,
                allowed_values=tuple(values_by_cf.get(cf_nr, ())),
            )
        )
    for members in features_by_class.values():
        members.sort(key=lambda f: (f.sort_nr, f.feature_id))

    synonyms_by_class: dict[str, list[str]] = defaultdict(list)
    for row in synonym_rows:
        synonyms_by_class[row["ARTCLASSID"]].append(row["CLASSSYNONYM"])

    classes: dict[str, EtimClass] = {}
    for row in class_rows:
        cid = row["ARTCLASSID"]
        gid = row["ARTGROUPID"]
        classes[cid] = EtimClass(
            class_id=cid,
            name=row["ARTCLASSDESC"],
            group_id=gid,
            group_name=groups.get(gid, ""),
            version=(row.get("ARTCLASSVERSION") or "").strip(),
            features=tuple(features_by_class.get(cid, ())),
            synonyms=tuple(synonyms_by_class.get(cid, ())),
        )

    return EtimModel(release=release, classes=classes, units=units)
