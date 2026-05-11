# -*- coding: utf-8 -*-
"""同场分组选片 MVP。

目标不是替代人工审美,而是给每张照片补充“同一组里排第几、建议怎么处理”。
当前规则偏保守:
- 优先按 EXIF 拍摄时间分组,相邻照片间隔不超过 gap_seconds 视为同场;
- 没有 EXIF 时,按文件名前缀 + 连续编号做弱分组;
- 每组按“综合评分”降序排序,同分时保持文件名顺序。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

GROUP_FIELDS = ["分组ID", "组内排名", "组内推荐", "组内说明"]


def read_capture_time(img: Path) -> datetime | None:
    """尝试从 EXIF 读取拍摄时间。失败返回 None。"""
    try:
        with Image.open(img) as im:
            ex = im.getexif()
            for tag in (0x9003, 0x0132):  # DateTimeOriginal, DateTime
                value = ex.get(tag)
                if not value:
                    continue
                text = str(value).strip()[:19]
                try:
                    return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        pass
    return None


def _score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("综合评分") or 0)
    except (TypeError, ValueError):
        return 0.0


def _filename_key(path: Path) -> tuple[str, int] | None:
    """提取类似 DSCF1234 / IMG_0001 的前缀和编号。"""
    match = re.match(r"^(.*?)(\d+)$", path.stem)
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def _group_with_capture_time(
    items: list[tuple[Path, dict[str, Any], datetime]],
    gap_seconds: int,
) -> list[list[tuple[Path, dict[str, Any]]]]:
    items = sorted(items, key=lambda x: (x[2], x[0].name.lower()))
    groups: list[list[tuple[Path, dict[str, Any]]]] = []
    current: list[tuple[Path, dict[str, Any]]] = []
    last_time: datetime | None = None
    for path, row, capture_time in items:
        if last_time is None or (capture_time - last_time).total_seconds() <= gap_seconds:
            current.append((path, row))
        else:
            if current:
                groups.append(current)
            current = [(path, row)]
        last_time = capture_time
    if current:
        groups.append(current)
    return groups


def _hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _bits_from_pixels(values: list[int], threshold: float) -> int:
    bits = 0
    for value in values:
        bits = (bits << 1) | int(value >= threshold)
    return bits


def _visual_signature(path: Path) -> tuple[int, int] | None:
    """读取图片的轻量视觉签名。

    不引入 imagehash 依赖,直接用 Pillow 做两个 64bit hash:
    - dHash: 看结构/边缘变化,适合近似重复图;
    - aHash: 看整体明暗块分布,降低纯色图误合并概率。
    """
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            dhash_img = gray.resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(dhash_img.tobytes())
            dhash = 0
            for row in range(8):
                offset = row * 9
                for col in range(8):
                    dhash = (dhash << 1) | int(pixels[offset + col] > pixels[offset + col + 1])

            ahash_img = gray.resize((8, 8), Image.Resampling.LANCZOS)
            avg_pixels = list(ahash_img.tobytes())
            ahash = _bits_from_pixels(avg_pixels, sum(avg_pixels) / len(avg_pixels))
            return dhash, ahash
    except Exception:  # noqa: BLE001
        return None


def _visual_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return _hamming_distance(left[0], right[0]) + _hamming_distance(left[1], right[1])


def _merge_groups_by_visual_similarity(
    groups: list[list[tuple[Path, dict[str, Any]]]],
    visual_threshold: int,
) -> list[list[tuple[Path, dict[str, Any]]]]:
    """把视觉上高度相似的单张组做并集合并。

    只合并“原本没有时间/文件名依据的单张组”。
    原因: EXIF 时间组和文件名连续组是更强信号,不能因为纯色图/弱 hash 误把不同场景合并。
    """
    if not groups:
        return groups

    eligible_indexes = [index for index, group in enumerate(groups) if len(group) == 1]
    if len(eligible_indexes) < 2:
        return groups

    signatures: dict[Path, tuple[int, int]] = {}
    for index in eligible_indexes:
        path = groups[index][0][0]
        if path.is_file():
            signature = _visual_signature(path)
            if signature is not None:
                signatures[path] = signature

    if len(signatures) < 2:
        return groups

    parent = {index: index for index in eligible_indexes}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for pos, i in enumerate(eligible_indexes):
        left = groups[i][0][0]
        if left not in signatures:
            continue
        for j in eligible_indexes[pos + 1 :]:
            right = groups[j][0][0]
            if right not in signatures:
                continue
            if _visual_distance(signatures[left], signatures[right]) <= visual_threshold:
                union(i, j)

    merged: dict[int, list[tuple[Path, dict[str, Any]]]] = {}
    consumed: set[int] = set()
    output: list[list[tuple[Path, dict[str, Any]]]] = []
    for index, group in enumerate(groups):
        if index not in parent:
            output.append(group)
            continue
        root = find(index)
        merged.setdefault(root, []).extend(group)
        if root not in consumed:
            output.append(merged[root])
            consumed.add(root)
    return output


def _group_by_filename(
    items: list[tuple[Path, dict[str, Any]]],
    max_number_gap: int = 3,
) -> list[list[tuple[Path, dict[str, Any]]]]:
    keyed: list[tuple[str, int, Path, dict[str, Any]]] = []
    singles: list[tuple[Path, dict[str, Any]]] = []
    for path, row in items:
        key = _filename_key(path)
        if key is None:
            singles.append((path, row))
        else:
            prefix, num = key
            keyed.append((prefix, num, path, row))

    keyed.sort(key=lambda x: (x[0], x[1], x[2].name.lower()))
    groups: list[list[tuple[Path, dict[str, Any]]]] = []
    current: list[tuple[Path, dict[str, Any]]] = []
    last_prefix: str | None = None
    last_num: int | None = None
    for prefix, num, path, row in keyed:
        same_series = prefix == last_prefix and last_num is not None and num - last_num <= max_number_gap
        if last_prefix is None or same_series:
            current.append((path, row))
        else:
            if current:
                groups.append(current)
            current = [(path, row)]
        last_prefix = prefix
        last_num = num
    if current:
        groups.append(current)
    groups.extend([[item] for item in sorted(singles, key=lambda x: x[0].name.lower())])
    return groups


def group_rows_for_selection(
    folder: Path,
    rows: list[dict[str, Any]],
    gap_seconds: int = 60,
    use_visual_similarity: bool = True,
    visual_threshold: int = 10,
) -> list[list[tuple[Path, dict[str, Any]]]]:
    """把 CSV 行按同场关系分组。"""
    with_time: list[tuple[Path, dict[str, Any], datetime]] = []
    without_time: list[tuple[Path, dict[str, Any]]] = []
    for row in rows:
        name = str(row.get("JPG文件名") or row.get("jpg_filename") or "").strip()
        if not name:
            continue
        path = folder / name
        capture_time = read_capture_time(path) if path.is_file() else None
        if capture_time is None:
            without_time.append((path, row))
        else:
            with_time.append((path, row, capture_time))

    groups = _group_with_capture_time(with_time, gap_seconds)
    groups.extend(_group_by_filename(without_time))
    if use_visual_similarity:
        groups = _merge_groups_by_visual_similarity(groups, visual_threshold=visual_threshold)
    return groups


def apply_group_selection_to_rows(
    folder: Path,
    rows: list[dict[str, Any]],
    gap_seconds: int = 60,
    use_visual_similarity: bool = True,
    visual_threshold: int = 10,
) -> list[dict[str, Any]]:
    """给每行补充 分组ID/组内排名/组内推荐/组内说明。原地修改并返回 rows。"""
    groups = group_rows_for_selection(
        folder,
        rows,
        gap_seconds=gap_seconds,
        use_visual_similarity=use_visual_similarity,
        visual_threshold=visual_threshold,
    )
    for group_index, group in enumerate(groups, start=1):
        group_id = f"G{group_index:04d}"
        ranked = sorted(group, key=lambda item: (-_score(item[1]), item[0].name.lower()))
        total = len(ranked)
        best_score = _score(ranked[0][1]) if ranked else 0
        for rank, (path, row) in enumerate(ranked, start=1):
            score = _score(row)
            row["分组ID"] = group_id
            row["组内排名"] = rank
            if total == 1:
                row["组内推荐"] = "单张"
                row["组内说明"] = "未找到同场相邻照片,按单张结果保留。"
            elif rank == 1:
                row["组内推荐"] = "精选"
                row["组内说明"] = f"本组 {total} 张中评分最高,建议优先看这张。"
            elif rank <= 2 and score >= max(7, best_score - 2):
                row["组内推荐"] = "备选"
                row["组内说明"] = "与本组最佳分差较小,可作为备选对比。"
            elif score <= 5:
                row["组内推荐"] = "淘汰"
                row["组内说明"] = "评分偏低,同组优先级靠后。"
            else:
                row["组内推荐"] = "保留"
                row["组内说明"] = "同组内不是首选,但分数未低到建议淘汰。"
            # 确保路径变量被真实使用,方便后续扩展到文件名说明。
            row.setdefault("JPG文件名", path.name)
    return rows
