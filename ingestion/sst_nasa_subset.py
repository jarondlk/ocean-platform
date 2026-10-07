"""Bounded NASA fallback qualification, separate from NOAA bulk acquisition.

Bearer credentials are read only from a private local file and sent to one
fixed HTTPS origin. A valid subset remains unapproved scientific raw evidence.
"""

from datetime import date
import hashlib
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np
import xarray as xr

from ingestion.immutable_bundle import digest
from ingestion.sst_acquisition import MAX_FILE_BYTES, VARIABLES, _download_locked
from ingestion.sst_hybrid_acquisition import EXCLUDED_DAYS, MAX_GRID_VALUES

HOST = "opendap.earthdata.nasa.gov"
COLLECTION = "C1996881146-POCLOUD"
MAX_PILOT_REQUESTS = 16


def nasa_subset_plan(descriptors):
    """At most sixteen independently bound, one-day native/coarse requests."""
    if not 1 <= len(descriptors) <= MAX_PILOT_REQUESTS:
        raise ValueError("NASA qualification requires 1–16 bounded subsets")
    requests = []
    for descriptor in descriptors:
        day, role, f = (
            descriptor["day"],
            descriptor["role"],
            descriptor["footprint"],
        )
        if (
            not date(2003, 1, 1) <= date.fromisoformat(day) < date.today()
            or day in EXCLUDED_DAYS
            or role not in {"context", "native_patch"}
            or set(f) != {"south", "north", "west", "east"}
        ):
            raise ValueError("Invalid NASA final-generation subset descriptor")
        south, north, west, east = (f[k] for k in ("south", "north", "west", "east"))
        stride = 5 if role == "context" else 1
        if (
            any(isinstance(v, bool) or not math.isfinite(v) for v in f.values())
            or not -89.9 <= south < north <= 89.9
            or not -179.9 <= west < east <= 179.9
            or (stride == 1 and (north - south > 0.121 or east - west > 0.121))
            or any(abs(v * 100 - round(v * 100)) > 1e-6 for v in f.values())
        ):
            raise ValueError("Invalid NASA acquisition envelope")
        # Native MUR axis origins verified from retained NASA originals. Every
        # response must independently confirm these coordinates and strides.
        y0, y1 = round((south + 89.99) * 100), round((north + 89.99) * 100)
        x0, x1 = round((west + 179.99) * 100), round((east + 179.99) * 100)
        values = ((y1 - y0) // stride + 1) * ((x1 - x0) // stride + 1)
        if values > MAX_GRID_VALUES:
            raise ValueError("NASA subset exceeds bounded grid contract")
        spatial = f"[0:1:0][{y0}:{stride}:{y1}][{x0}:{stride}:{x1}]"
        query = ";".join(
            [v + spatial for v in VARIABLES]
            + [f"lat[{y0}:{stride}:{y1}]", f"lon[{x0}:{stride}:{x1}]", "time[0:1:0]"]
        )
        granule = (
            day.replace("-", "") + "090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1"
        )
        requests.append(
            {
                "day": day,
                "role": role,
                "location_id": descriptor.get("location_id"),
                "footprint": f,
                "spatial_stride": stride,
                "expected_time_utc": day + "T09:00:00Z",
                "source_url": f"https://{HOST}/collections/{COLLECTION}/granules/{granule}.dap.nc4?dap4.ce="
                + quote(query, safe=""),
            }
        )
    if len({digest(r) for r in requests}) != len(requests):
        raise ValueError("Duplicate NASA qualification request")
    plan = {
        "schema_version": 1,
        "kind": "nasa_mur_hybrid_qualification",
        "provider": "nasa_podaac",
        "collection": COLLECTION,
        "product_version": "04.1",
        "maximum_download_bytes": len(requests) * MAX_FILE_BYTES,
        "scientific_approval": False,
        "scientific_publication": False,
        "requests": requests,
    }
    if len(requests) == 1:
        plan["role"] = requests[0]["role"]
    return {**plan, "plan_sha256": digest(plan)}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("NASA credential redirect forbidden")


def nasa_opener(credential_path, *, transport=None):
    path = Path(credential_path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("NASA credential symlink forbidden")
    with path.open("rb") as handle:
        s = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_uid != os.getuid()
            or s.st_mode & 0o077
            or not 1 <= s.st_size <= 8192
        ):
            raise ValueError("NASA credential must be an owned private regular file")
        raw = handle.read(8193)
    try:
        secret = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        raise ValueError("Invalid private Earthdata bearer format") from None
    if (
        len(secret) <= 100
        or secret.count(".") != 2
        or any(not (c.isalnum() or c in "-_.") for c in secret)
    ):
        raise ValueError("Invalid private Earthdata bearer format")
    transport = transport or build_opener(_NoRedirect())

    class Authenticated:
        def open(self, url, *, timeout):
            target = urlsplit(url)
            if (
                target.scheme != "https"
                or target.hostname != HOST
                or target.port not in (None, 443)
                or target.username
                or target.password
                or target.fragment
                or not target.path.startswith(f"/collections/{COLLECTION}/granules/")
            ):
                raise ValueError("NASA credential destination forbidden")
            return transport.open(
                Request(
                    url,
                    headers={
                        "Authorization": "Bearer " + secret,
                        "Accept-Encoding": "identity",
                    },
                ),
                timeout=timeout,
            )

    return Authenticated()


def download_nasa_pilot(
    plan, directory, credential_path, *, transport=None, attempts=3, sleep=time.sleep
):
    descriptors = [
        {k: r[k] for k in ("day", "role", "footprint", "location_id")}
        for r in plan["requests"]
    ]
    if plan != nasa_subset_plan(descriptors):
        raise ValueError("NASA qualification plan binding mismatch")
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= 5
    ):
        raise ValueError("Invalid NASA qualification retry limit")
    opener = nasa_opener(credential_path, transport=transport)
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("NASA staging symlink forbidden")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = directory / ".acquisition.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        return _download_locked(plan, directory, attempts, False, opener, sleep)
    finally:
        lock.unlink()


def validate_nasa_pilot(manifest, contents, plan, *, archive_interim=False):
    if (
        manifest.get("plan") != plan
        or manifest.get("status") != "complete_unapproved_acquisition"
        or len(manifest.get("files", [])) != len(plan["requests"])
    ):
        raise ValueError("Incomplete NASA qualification acquisition")
    # Independently reconstruct both the plan and exact request/file ordering.
    if plan != nasa_subset_plan(
        [
            {k: r[k] for k in ("day", "role", "footprint", "location_id")}
            for r in plan["requests"]
        ]
    ):
        raise ValueError("NASA qualification plan binding mismatch")
    diagnostics = []
    for entry, request in zip(manifest["files"], plan["requests"]):
        if any(entry.get(k) != v for k, v in request.items()):
            raise ValueError("NASA raw request binding mismatch")
        data = contents[entry["filename"]]
        sha = hashlib.sha256(data).hexdigest()
        if (
            len(data) != entry["bytes"]
            or len(data) > MAX_FILE_BYTES
            or sha != entry["raw_sha256"]
            or entry["filename"] != entry["day"] + "-" + sha + ".nc"
            or entry["granule_id"]
            != digest({"source_url": request["source_url"], "raw_sha256": sha})
        ):
            raise ValueError("NASA raw byte/identity mismatch")
        # netCDF4 reads HDF5 via a real temporary file; the NOAA byte-buffer
        # reader contract cannot be assumed for NASA's compressed containers.
        with tempfile.TemporaryDirectory(prefix="nasa-mur-validate-") as tmp:
            path = Path(tmp) / "subset.nc"
            path.write_bytes(data)
            path.chmod(0o600)
            with xr.open_dataset(path) as ds:
                version, title = ds.attrs.get("product_version"), ds.attrs.get("title")
                generation = (
                    "final"
                    if version == "04.1" and title == "Daily MUR SST, Final product"
                    else "interim"
                    if version == "04.1nrt"
                    and title == "Daily MUR SST, Interim near-real-time (nrt) product"
                    else "unknown"
                )
                if (
                    generation == "unknown"
                    or (generation == "interim" and not archive_interim)
                    or set(("time", "lat", "lon", *VARIABLES)) - set(ds.variables)
                    or ds.analysed_sst.attrs.get("units") != "kelvin"
                    or ds.analysis_error.attrs.get("units") != "kelvin"
                    or ds.analysed_sst.size > MAX_GRID_VALUES
                    or any(ds[v].dims != ("time", "lat", "lon") for v in VARIABLES)
                ):
                    raise ValueError("NASA final MUR metadata/fields mismatch")
                if [
                    np.datetime_as_string(t, unit="s") + "Z" for t in ds.time.values
                ] != [request["expected_time_utc"]]:
                    raise ValueError("NASA actual timestamp mismatch")
                f, stride = request["footprint"], request["spatial_stride"]
                for name, origin, low, high in (
                    ("lat", -89.99, f["south"], f["north"]),
                    ("lon", -179.99, f["west"], f["east"]),
                ):
                    first = round((low - origin) * 100)
                    last = round((high - origin) * 100)
                    expected = origin + np.arange(first, last + 1, stride) / 100
                    actual = ds[name].values
                    if actual.shape != expected.shape or not np.allclose(
                        actual, expected, rtol=0, atol=2e-5
                    ):
                        raise ValueError("NASA grid stride/coverage mismatch")
                finite = int(
                    (
                        (ds["mask"].values == 1) & np.isfinite(ds.analysed_sst.values)
                    ).sum()
                )
                diagnostics.append(
                    {
                        "day": request["day"],
                        "role": request["role"],
                        "finite_ocean_pixels": finite,
                        "raw_bytes": len(data),
                        "processing_generation": generation,
                        "eligible_for_final_series": generation == "final",
                        "scientific_approval": False,
                    }
                )
    result = {
        "kind": "nasa_hybrid_subset_qualification",
        "plan_sha256": plan["plan_sha256"],
        "requests": diagnostics,
        "raw_bytes": sum(r["raw_bytes"] for r in diagnostics),
        "scientific_approval": False,
        "scientific_quality_threshold_applied": False,
        "scientific_publication": False,
    }
    if len(diagnostics) == 1:
        result["processing_generation"] = diagnostics[0]["processing_generation"]
    return result
