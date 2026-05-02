from pathlib import Path


def resolve_review_destination(base_archive: Path, series_names: list[str]) -> Path:
    if len(series_names) > 1:
        return base_archive / "_multi_series"
    if len(series_names) == 1:
        return base_archive / series_names[0]
    return base_archive / "_pending"
