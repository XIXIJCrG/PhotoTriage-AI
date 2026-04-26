# -*- coding: utf-8 -*-
"""Prompt profiles 管理。

profiles 存储在 ~/.triage_cache/prompts.json。
始终保留一个名为「默认」的 profile,文本来自 triage.PROMPT。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from triage import PROMPT as DEFAULT_PROMPT


DEFAULT_PROFILE_NAME = "默认"


@dataclass
class PromptProfile:
    name: str
    prompt: str
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {"name": self.name, "prompt": self.prompt,
                "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "PromptProfile":
        return cls(name=d.get("name", ""),
                   prompt=d.get("prompt", ""),
                   updated_at=d.get("updated_at", ""))


class PromptStore:
    """Prompt profiles 的持久化。"""

    def __init__(self, path: Path | None = None):
        self.path = path or (Path.home() / ".triage_cache" / "prompts.json")
        self._profiles: dict[str, PromptProfile] = {}
        self._load()
        # 保证"默认"存在且内容是最新的 triage.PROMPT
        self._profiles[DEFAULT_PROFILE_NAME] = PromptProfile(
            name=DEFAULT_PROFILE_NAME, prompt=DEFAULT_PROMPT)

    def _load(self):
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for d in data.get("profiles", []):
                p = PromptProfile.from_dict(d)
                if p.name:
                    self._profiles[p.name] = p
        except Exception as e:  # noqa: BLE001
            # 文件损坏 → 备份保留,避免 save() 覆盖掉用户数据
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = self.path.with_name(f"{self.path.stem}.bak.{stamp}.json")
                self.path.rename(backup)
                print(f"[PromptStore] 读取失败已备份到 {backup}: {e}")
            except Exception:  # noqa: BLE001
                pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 不把"默认"写进去(它直接读 triage.PROMPT)
        data = {
            "profiles": [p.to_dict() for n, p in self._profiles.items()
                         if n != DEFAULT_PROFILE_NAME],
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def list_names(self) -> list[str]:
        """返回所有 profile 名,默认永远排第一。"""
        names = [n for n in self._profiles if n != DEFAULT_PROFILE_NAME]
        names.sort()
        return [DEFAULT_PROFILE_NAME] + names

    def get(self, name: str) -> PromptProfile | None:
        return self._profiles.get(name)

    def upsert(self, name: str, prompt: str) -> PromptProfile:
        p = PromptProfile(name=name, prompt=prompt)
        self._profiles[name] = p
        if name != DEFAULT_PROFILE_NAME:
            self.save()
        return p

    def delete(self, name: str) -> bool:
        if name == DEFAULT_PROFILE_NAME:
            return False
        if name not in self._profiles:
            return False
        del self._profiles[name]
        self.save()
        return True
