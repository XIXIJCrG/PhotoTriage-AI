# -*- coding: utf-8 -*-
"""
照片批量初筛工具 — 使用 OpenAI-compatible 视觉模型对 JPG+RAW 照片做客观评价,
输出 CSV,并把星级/标题/标记/备注写入 XMP(JPG 内嵌,RAW 写 sidecar)。
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import re
import signal
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from PIL import Image, ImageOps
from tqdm import tqdm

from core.providers import auth_headers, chat_completions_url, is_local_provider, models_url

# Windows 控制台默认 GBK,强制 UTF-8 以正确显示中文和符号
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ========== 用户配置 ==========

API_URL = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_BASE_URL = API_URL.replace("/chat/completions", "")
DEFAULT_MODEL = "local-vision-model"
PHOTO_FOLDER = "."

TIMEOUT = 180
MAX_IMAGE_SIZE = 1024
TEMPERATURE = 0.3
MAX_TOKENS = 1800
# Some local multimodal models support a thinking mode that can consume output tokens.
DISABLE_THINKING = True
SKIP_PROCESSED = True
MAX_RETRIES = 2
WRITE_METADATA = True
METADATA_MODE = "embed"  # embed: 写入 JPG/PNG, sidecar: 只生成 .xmp sidecar
# 并发数默认值 — 必须 ≤ llama-server 的 --parallel 值。
# 常规服务(--parallel 4)用 4;triage 专用服务(--parallel 8)用 8。
# 命令行 --concurrency N 可覆盖。
CONCURRENCY = 8

# ========== 配置结束 ==========


JPG_EXT = {".jpg", ".jpeg"}
PNG_EXT = {".png"}
IMG_EXT = JPG_EXT | PNG_EXT
RAW_EXT = {".raf", ".arw", ".cr2", ".cr3", ".nef", ".dng"}

SCENE_CN = {
    "street": "街拍", "landscape": "风光", "portrait": "人像",
    "still_life": "静物", "architecture": "建筑", "animal": "动物",
    "night": "夜景", "macro": "微距", "food": "美食",
    "event": "活动", "other": "其他",
}
TIME_CN = {
    "dawn": "黎明", "morning": "早晨", "noon": "正午",
    "afternoon": "下午", "golden_hour": "黄金时刻",
    "blue_hour": "蓝调时刻", "night": "夜晚",
    "indoor": "室内", "unknown": "未知",
}
INTENT_CN = {
    "candid": "抓拍", "posed": "摆拍", "studio": "棚拍",
    "documentary": "纪实", "casual": "随手", "artistic": "艺术创作",
    "unknown": "未知",
}

PROMPT = """你是一位资深摄影评审,对好照片有共情,会先读懂一张照片再做评价。
拿到照片后请按这个思路:
  1. 先看画面在表达什么——主体、瞬间、情绪、光影氛围
  2. 识别这张照片的类型和意图(抓拍/摆拍/棚拍/纪实/随手/艺术创作)
  3. 按该类型的审美标准评价——不拿风光标准套人像,不拿纪实标准套棚拍
  4. 找出画面里"对"的地方,讲到具体细节,不要只说空话
  5. 只在真正影响观感时才指出问题,无伤大雅的不必列

请严格按以下 JSON 格式输出,不要添加任何解释文字:

{
  "content": {
    "scene_type": "street/landscape/portrait/still_life/architecture/animal/night/macro/food/event/other",
    "primary_subject": "一句话描述主体(20字内,中文)",
    "impression": "画面在讲什么、摄影师想表达什么(40字内,中文)",
    "shooting_intent": "candid/posed/studio/documentary/casual/artistic/unknown",
    "has_person": true/false,
    "person_count": 数字,
    "time_of_day": "dawn/morning/noon/afternoon/golden_hour/blue_hour/night/indoor/unknown",
    "dominant_colors": ["主要色调1", "主要色调2", "主要色调3"]
  },
  "technical": {
    "sharpness": 对焦清晰度 1-5,
    "exposure": 曝光 1-5 (3=正确, <3=欠曝, >3=过曝),
    "noise_level": 噪点 1-5 (1=几乎无, 5=严重),
    "white_balance": 白平衡 1-5,
    "has_motion_blur": true/false,
    "is_motion_blur_intentional": true/false/null
  },
  "aesthetic": {
    "composition": 构图 1-10,
    "lighting": 光线质量 1-10,
    "color": 色彩 1-10,
    "subject_clarity": 主体突出度 1-10,
    "storytelling": 叙事感/瞬间感 1-10,
    "uniqueness": 独特性 1-10
  },
  "portrait": {
    "expression": 神态 1-10,
    "pose": 姿态 1-10,
    "eye_contact": 眼神 1-10,
    "flattering": 美感表达 1-10,
    "portrait_note": "一句话点评这一帧人物状态(30字内,中文)"
  },
  "overall": {
    "technical_score": 技术总分 1-10,
    "aesthetic_score": 艺术总分 1-10,
    "overall_score": 综合评分 1-10,
    "strengths": ["具体优点1", "具体优点2"],
    "weaknesses": ["真问题1", "真问题2"],
    "one_line_comment": "一句话总评(30字内)"
  }
}

"portrait" 字段只在 scene_type="portrait" 时需要填。非人像请把整个 portrait 对象设为 null。

人像评分要点(重要):
人像选片的核心不是构图光线色彩(同场拍摄这些几乎一致),而是**这一帧把人拍好看了没有**。
请按这四个维度认真打分:
- expression(神态): 1=僵硬/无神/表情扭曲, 5=自然但平淡, 8=生动有感染力, 10=绝佳瞬间
- pose(姿态): 1=别扭拘谨/手脚不知道放哪, 5=普通合格, 8=舒展自然有设计感, 10=极具表现力
- eye_contact(眼神): 这一项评价的是**眼睛的质量**,不是"有没有看镜头"。
    * 看镜头 / 看远方 / 看侧面 / 闭目沉思都可以是好眼神——关键是眼神状态
    * 高分(8-10): 眼睛明亮有聚焦点、带情绪、有神采、视线方向贴合气氛(比如若有所思的侧视、坚定直视、含笑低垂)
    * 中等(5-7): 眼睛清晰正常但情绪一般,没什么特别打动人
    * 低分(1-4): 眯眼/半闭眼、眼神涣散无聚焦、眼白过多显得呆滞、眼睛被头发/阴影遮住、眼神明显迷茫或疲态
    * 不要因为没看镜头就降分;也不要因为看了镜头就加分。只看眼睛本身的质量。
- flattering(美感表达): 1=角度/光线/瞬间都不利于人物, 5=中性, 8=这一帧显得比平均好看, 10=把人拍得极美
- portrait_note: 像朋友讨论选片那样直接说出来(比如"嘴角有点僵"/"这张侧光把下颌勾得很好"/"眼神在发呆")

人像评分请放开评价。评价一张人像照片"这一帧拍得人好不好看"是审片的本职工作,不是冒犯。
不要因为怕得罪人就全给 7 分——那等于没评。朋友帮你选片时,她会直接说"这张眼神散了"或"这张最好看",请用那种直率。

评分锚点(overall_score):
- <5: 废片——严重失焦 / 严重曝光 / 闭眼/表情扭曲且无补救
- 5-6: 平庸——没有明显缺陷但也不出彩,像手机随手拍
- 7: 合格——可以留存,同场拍摄里的普通一张(找不到缺陷时默认 7)
- 8: 明显好于同场平均——某个维度(神态/光线/构图/瞬间)突出
- 9: 一眼想挑出来重点修的那张——多项俱佳
- 10: 罕见的决定性瞬间或大师级画面,慎用

对人像照片,overall_score 请以 portrait 四项(神态/姿态/眼神/美感)为主要依据,
其次是光线对人物的塑造,再次是构图。构图/色彩在同场拍摄里的细微差别不必过度加权。
同场多张人像请拉开分差——如果你给 50 张全打 7,等于没挑。

strengths 和 weaknesses 的写法:
- strengths 必须具体。人像写"侧逆光在下颌线形成干净的轮廓高光"/"眼神带笑意且有聚焦点",
  不要写"光线柔和"/"神态自然"这种废话。
- weaknesses 只列真问题。人像常见真问题:眼神无光、表情僵硬、姿态别扭、下巴/颈部角度不利、
  前景杂物干扰、面部阴影过重。不确定就不要写。weaknesses 可以为空数组 []。

按题材标准评价:
- 人像(posed/studio):重心在 portrait 四项;看神态/眼神/姿态/光线塑形
- 街拍/纪实:看瞬间、故事感、环境与人物的呼应
- 风光:看光线、层次、构图、氛围
- 随手抓拍:门槛降低,看是否有记录价值或情绪

字符串字段用中文(除枚举值外),严格按 JSON 输出。
"""


# ---------- 文件扫描 ----------

def scan_folder(folder: Path) -> list[tuple[Path, Optional[Path]]]:
    """返回 [(img_path, raw_path_or_None), ...],按文件名排序。支持 JPG/PNG。"""
    files = list(folder.iterdir())
    imgs = sorted([f for f in files if f.suffix.lower() in IMG_EXT])
    raw_map: dict[str, Path] = {}
    for f in files:
        if f.suffix.lower() in RAW_EXT:
            raw_map[f.stem] = f
    return [(j, raw_map.get(j.stem)) for j in imgs]


# ---------- 图片预处理 ----------

def encode_image(jpg_path: Path, max_size: int = MAX_IMAGE_SIZE) -> str:
    with Image.open(jpg_path) as im:
        # 按 EXIF Orientation 把竖拍/旋转过的照片摆正
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > max_size:
            if w >= h:
                new_w, new_h = max_size, int(h * max_size / w)
            else:
                new_w, new_h = int(w * max_size / h), max_size
            im = im.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- 模型调用 ----------

def parse_response(text: str) -> dict[str, Any]:
    text = text.strip()
    # 去掉 markdown 代码围栏
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"_error": "JSON 解析失败", "_raw": text[:500]}


def analyze_image(
    jpg_path: Path,
    prompt: Optional[str] = None,
    api_url: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    provider_type: Optional[str] = None,
) -> dict[str, Any]:
    b64 = encode_image(jpg_path)
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    if DISABLE_THINKING and is_local_provider(provider_type):
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    url = api_url or chat_completions_url(base_url or DEFAULT_BASE_URL)
    headers = auth_headers(api_key)
    last_err: Optional[str] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                continue
            content = r.json()["choices"][0]["message"]["content"]
            result = parse_response(content)
            if "_error" in result:
                last_err = result["_error"]
                if attempt < MAX_RETRIES:
                    continue
            return result
        except requests.exceptions.ConnectionError as e:
            # Model service is unreachable; stop the batch early.
            raise RuntimeError(f"模型服务连接失败: {e}") from e
        except requests.exceptions.Timeout:
            last_err = f"超时 (>{TIMEOUT}s)"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
    return {"_error": last_err or "未知错误"}


# ---------- XMP 生成和写入 ----------

XMP_NS_MARKER = b"http://ns.adobe.com/xap/1.0/\x00"


def score_to_rating(score: int) -> int:
    """1-2→1★, 3-4→2★, 5-6→3★, 7-8→4★, 9-10→5★"""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return 0
    if s <= 0: return 0
    if s <= 2: return 1
    if s <= 4: return 2
    if s <= 6: return 3
    if s <= 8: return 4
    return 5


# Microsoft 照片应用用的 0-99 分级值
MS_RATING_MAP = {0: 0, 1: 1, 2: 25, 3: 50, 4: 75, 5: 99}


def xml_escape(s: str) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;"))


def build_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """从分析结果构建要写入的元数据(全部中文字符串)。"""
    content = result.get("content", {}) or {}
    tech = result.get("technical", {}) or {}
    aes = result.get("aesthetic", {}) or {}
    port = result.get("portrait") or {}
    ov = result.get("overall", {}) or {}

    scene_en = str(content.get("scene_type", "other"))
    scene_cn = SCENE_CN.get(scene_en, scene_en)
    time_en = str(content.get("time_of_day", "unknown"))
    time_cn = TIME_CN.get(time_en, time_en)
    intent_en = str(content.get("shooting_intent", "unknown"))
    intent_cn = INTENT_CN.get(intent_en, intent_en)

    primary = str(content.get("primary_subject", "")).strip()
    impression = str(content.get("impression", "")).strip()
    one_line = str(ov.get("one_line_comment", "")).strip()
    strengths = [str(x).strip() for x in (ov.get("strengths") or []) if str(x).strip()]
    weaknesses = [str(x).strip() for x in (ov.get("weaknesses") or []) if str(x).strip()]

    overall_score = ov.get("overall_score", 0)
    tech_score = ov.get("technical_score", 0)
    aes_score = ov.get("aesthetic_score", 0)

    title = f"[{overall_score}分] {primary}" if primary else f"综合{overall_score}分"
    subject = one_line or primary

    tags = [scene_cn, time_cn]
    for s in strengths[:2]:
        if len(s) <= 12 and s not in tags:
            tags.append(s)

    comment_lines = [
        f"综合 {overall_score}/10  技术 {tech_score}  艺术 {aes_score}",
        f"场景: {scene_cn}  意图: {intent_cn}  时段: {time_cn}",
    ]
    if primary:
        comment_lines.append(f"主体: {primary}")
    if impression:
        comment_lines.append(f"感受: {impression}")
    # 人像照片追加人像专项
    if port and scene_en == "portrait":
        exp = port.get("expression")
        pose = port.get("pose")
        eye = port.get("eye_contact")
        flat = port.get("flattering")
        note = str(port.get("portrait_note", "") or "").strip()
        if any(v is not None for v in (exp, pose, eye, flat)):
            comment_lines.append(
                f"人像: 神态{exp} 姿态{pose} 眼神{eye} 美感{flat}"
            )
        if note:
            comment_lines.append(f"人像点评: {note}")
    if strengths:
        comment_lines.append("优点: " + " | ".join(strengths))
    if weaknesses:
        comment_lines.append("问题: " + " | ".join(weaknesses))
    if one_line:
        comment_lines.append(f"总评: {one_line}")
    comment = "\n".join(comment_lines)

    return {
        "title": title,
        "subject": subject,
        "rating": score_to_rating(overall_score),
        "tags": tags,
        "comment": comment,
    }


def build_xmp(meta: dict[str, Any]) -> str:
    """生成 XMP packet(UTF-8 XML 字符串)。"""
    title = xml_escape(meta["title"])
    subject = xml_escape(meta["subject"])
    comment = xml_escape(meta["comment"])
    rating = int(meta["rating"])
    ms_rating = MS_RATING_MAP.get(rating, 0)
    tags_xml = "\n        ".join(
        f"<rdf:li>{xml_escape(t)}</rdf:li>" for t in meta["tags"] if t
    )

    return f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="PhotoTriage">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
    xmlns:exif="http://ns.adobe.com/exif/1.0/"
    xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/">
   <dc:title>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{title}</rdf:li>
    </rdf:Alt>
   </dc:title>
   <dc:description>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{comment}</rdf:li>
    </rdf:Alt>
   </dc:description>
   <dc:subject>
    <rdf:Bag>
        {tags_xml}
    </rdf:Bag>
   </dc:subject>
   <xmp:Rating>{rating}</xmp:Rating>
   <MicrosoftPhoto:Rating>{ms_rating}</MicrosoftPhoto:Rating>
   <photoshop:Headline>{subject}</photoshop:Headline>
   <exif:UserComment>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{comment}</rdf:li>
    </rdf:Alt>
   </exif:UserComment>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''


def embed_xmp_in_jpeg(jpg_path: Path, xmp_xml: str) -> None:
    """把 XMP 作为 APP1 段嵌入 JPEG,移除已有的 XMP 段。"""
    data = jpg_path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"不是 JPEG: {jpg_path}")

    xmp_bytes = xmp_xml.encode("utf-8")
    payload = XMP_NS_MARKER + xmp_bytes
    seg_len = len(payload) + 2
    if seg_len > 0xFFFF:
        # XMP 太大,塞不进单段。初筛场景下不会触发,但保底裁剪一下。
        max_body = 0xFFFF - 2 - len(XMP_NS_MARKER)
        payload = XMP_NS_MARKER + xmp_bytes[:max_body]
        seg_len = len(payload) + 2
    new_xmp_seg = b"\xff\xe1" + seg_len.to_bytes(2, "big") + payload

    out = bytearray()
    out.extend(data[:2])  # SOI
    out.extend(new_xmp_seg)  # 新 XMP 紧跟 SOI

    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            out.extend(data[i:])
            break
        marker = data[i + 1]
        if marker == 0xFF:
            out.append(0xFF)
            i += 1
            continue
        if marker == 0x00:
            out.extend(data[i:i + 2])
            i += 2
            continue
        if marker == 0xDA:  # SOS: 剩下的全是熵编码数据
            out.extend(data[i:])
            break
        if marker == 0xD9 or (0xD0 <= marker <= 0xD7):
            out.extend(data[i:i + 2])
            i += 2
            continue
        if i + 4 > n:
            out.extend(data[i:])
            break
        seg_len_ex = int.from_bytes(data[i + 2:i + 4], "big")
        seg_end = i + 2 + seg_len_ex
        # 移除已有 XMP APP1
        if (marker == 0xE1
                and i + 4 + len(XMP_NS_MARKER) <= n
                and data[i + 4:i + 4 + len(XMP_NS_MARKER)] == XMP_NS_MARKER):
            i = seg_end
            continue
        out.extend(data[i:seg_end])
        i = seg_end

    jpg_path.write_bytes(bytes(out))


def write_xmp_sidecar(raw_path: Path, xmp_xml: str) -> None:
    """为 RAW 写 sidecar: DSCF6034.RAF -> DSCF6034.xmp"""
    sidecar = raw_path.with_suffix(".xmp")
    sidecar.write_text(xmp_xml, encoding="utf-8")


PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_XMP_KEYWORD = b"XML:com.adobe.xmp"


def embed_xmp_in_png(png_path: Path, xmp_xml: str) -> None:
    """把 XMP 作为 iTXt chunk 嵌入 PNG,移除已有的 XMP iTXt chunk。"""
    import zlib
    data = png_path.read_bytes()
    if data[:8] != PNG_SIG:
        raise ValueError(f"不是 PNG: {png_path}")

    xmp_bytes = xmp_xml.encode("utf-8")
    # iTXt 数据体: 关键字 \0 压缩标志 压缩方法 语言\0 翻译关键字\0 文本
    itxt_data = (PNG_XMP_KEYWORD + b"\x00"
                 + b"\x00\x00"        # 压缩标志=0 压缩方法=0
                 + b"\x00"            # 语言(空) \0
                 + b"\x00"            # 翻译关键字(空) \0
                 + xmp_bytes)
    chunk_type = b"iTXt"
    crc = zlib.crc32(chunk_type + itxt_data) & 0xFFFFFFFF
    new_itxt = (len(itxt_data).to_bytes(4, "big") + chunk_type
                + itxt_data + crc.to_bytes(4, "big"))

    # 遍历 chunk,跳过已有的 XMP iTXt,在 IEND 前插入新的
    out = bytearray(PNG_SIG)
    i = 8
    n = len(data)
    inserted = False
    while i < n:
        if i + 8 > n:
            out.extend(data[i:])
            break
        clen = int.from_bytes(data[i:i + 4], "big")
        ctype = data[i + 4:i + 8]
        cend = i + 8 + clen + 4  # 长度 + 类型 + 数据 + CRC
        if ctype == b"IEND":
            if not inserted:
                out.extend(new_itxt)
                inserted = True
            out.extend(data[i:cend])
            i = cend
            continue
        if ctype == b"iTXt":
            cdata = data[i + 8:i + 8 + clen]
            if cdata.startswith(PNG_XMP_KEYWORD + b"\x00"):
                # 已有的 XMP chunk,跳过
                i = cend
                continue
        out.extend(data[i:cend])
        i = cend

    if not inserted:
        raise ValueError(f"PNG 没有 IEND chunk: {png_path}")
    png_path.write_bytes(bytes(out))


def embed_xmp(img_path: Path, xmp_xml: str) -> None:
    """按扩展名分发到 JPEG 或 PNG 嵌入器。"""
    ext = img_path.suffix.lower()
    if ext in JPG_EXT:
        embed_xmp_in_jpeg(img_path, xmp_xml)
    elif ext in PNG_EXT:
        embed_xmp_in_png(img_path, xmp_xml)
    else:
        raise ValueError(f"不支持嵌入 XMP 的格式: {ext}")


# ---------- CSV ----------

CSV_FIELDS = [
    "JPG文件名", "RAW文件名", "有RAW",
    "场景", "拍摄意图", "主体", "画面感受",
    "有人", "人数", "时段", "主色调",
    "对焦", "曝光", "噪点", "白平衡",
    "动态模糊", "动态模糊是否有意",
    "构图", "光线", "色彩", "主体突出",
    "叙事感", "独特性",
    "神态", "姿态", "眼神", "美感", "人像点评",
    "技术总分", "艺术总分", "综合评分",
    "优点", "问题", "一句话总评",
    "耗时秒", "错误",
]


def _g(d: dict, key: str, default: Any = "") -> Any:
    v = d.get(key, default) if isinstance(d, dict) else default
    return default if v is None else v


def _bool_cn(v: Any) -> Any:
    if v is True:
        return "是"
    if v is False:
        return "否"
    return v  # None / 空串保持原样


def _clean(v: Any) -> Any:
    """去掉模型偶尔生成的换行/回车,避免 Excel 单元格撑高显得像空行。"""
    if isinstance(v, str):
        return v.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    return v


def result_to_row(jpg: Path, raw: Optional[Path], result: dict[str, Any],
                  elapsed: float) -> dict[str, Any]:
    err = result.get("_error", "")
    content = result.get("content", {}) or {}
    tech = result.get("technical", {}) or {}
    aes = result.get("aesthetic", {}) or {}
    port = result.get("portrait") or {}  # 非人像时可能是 null
    ov = result.get("overall", {}) or {}

    colors = content.get("dominant_colors") or []
    if not isinstance(colors, list):
        colors = [str(colors)]
    strengths = ov.get("strengths") or []
    if not isinstance(strengths, list):
        strengths = [str(strengths)]
    weaknesses = ov.get("weaknesses") or []
    if not isinstance(weaknesses, list):
        weaknesses = [str(weaknesses)]

    scene_en = _g(content, "scene_type")
    time_en = _g(content, "time_of_day")
    intent_en = _g(content, "shooting_intent")

    row = {
        "JPG文件名": jpg.name,
        "RAW文件名": raw.name if raw else "",
        "有RAW": _bool_cn(bool(raw)),
        "场景": SCENE_CN.get(str(scene_en), scene_en),
        "拍摄意图": INTENT_CN.get(str(intent_en), intent_en),
        "主体": _g(content, "primary_subject"),
        "画面感受": _g(content, "impression"),
        "有人": _bool_cn(_g(content, "has_person")),
        "人数": _g(content, "person_count"),
        "时段": TIME_CN.get(str(time_en), time_en),
        "主色调": ",".join(str(c) for c in colors),
        "对焦": _g(tech, "sharpness"),
        "曝光": _g(tech, "exposure"),
        "噪点": _g(tech, "noise_level"),
        "白平衡": _g(tech, "white_balance"),
        "动态模糊": _bool_cn(_g(tech, "has_motion_blur")),
        "动态模糊是否有意": _bool_cn(_g(tech, "is_motion_blur_intentional")),
        "构图": _g(aes, "composition"),
        "光线": _g(aes, "lighting"),
        "色彩": _g(aes, "color"),
        "主体突出": _g(aes, "subject_clarity"),
        "叙事感": _g(aes, "storytelling"),
        "独特性": _g(aes, "uniqueness"),
        "神态": _g(port, "expression"),
        "姿态": _g(port, "pose"),
        "眼神": _g(port, "eye_contact"),
        "美感": _g(port, "flattering"),
        "人像点评": _g(port, "portrait_note"),
        "技术总分": _g(ov, "technical_score"),
        "艺术总分": _g(ov, "aesthetic_score"),
        "综合评分": _g(ov, "overall_score"),
        "优点": "|".join(str(s) for s in strengths),
        "问题": "|".join(str(s) for s in weaknesses),
        "一句话总评": _g(ov, "one_line_comment"),
        "耗时秒": round(elapsed, 2),
        "错误": err,
    }
    # 把所有字符串字段的换行符换成空格,避免 Excel 显示撑行
    return {k: _clean(v) for k, v in row.items()}


def load_processed(folder: Path) -> tuple[Optional[Path], set[str]]:
    """返回 (最新 CSV 路径, 已处理的 jpg 文件名集合)。兼容旧英文表头。"""
    csvs = sorted(folder.glob("triage_*.csv"))
    if not csvs:
        return None, set()
    latest = csvs[-1]
    done: set[str] = set()
    try:
        with latest.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("JPG文件名") or row.get("jpg_filename") or "").strip()
                err = (row.get("错误") or row.get("error") or "").strip()
                if name and not err:
                    done.add(name)
    except Exception:
        return None, set()
    return latest, done


# ---------- 主流程 ----------

_interrupted = False


def _sigint_handler(signum, frame):  # noqa: ARG001
    global _interrupted
    if _interrupted:
        print("\n强制退出。", file=sys.stderr)
        sys.exit(130)
    _interrupted = True
    print("\n收到中断信号,处理完当前照片后退出...", file=sys.stderr)


def check_server(
    api_url: str = API_URL,
    timeout: float = 5,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[bool, str]:
    """检查 OpenAI-compatible model endpoint 是否在线。返回 (ok, message)。"""
    url = models_url(base_url or api_url)
    headers = auth_headers(api_key)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        data = r.json()
        models = (data.get("data") or data.get("models") or [])
        if not models:
            return False, "未返回模型列表"
        names = [m.get("id") or m.get("name") for m in models if isinstance(m, dict)]
        names = [n for n in names if n]
        if model and model in names:
            return True, model
        return True, names[0] if names else "unknown"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def run_batch(
    folder: Path,
    concurrency: int = CONCURRENCY,
    write_meta: bool = True,
    metadata_mode: str = METADATA_MODE,
    limit: int = 0,
    skip_processed: bool = SKIP_PROCESSED,
    prompt: Optional[str] = None,
    prompt_label: str = "",
    api_url: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    provider_type: Optional[str] = None,
    on_progress: Optional[Callable[[Path, dict, int, int], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    """批处理主逻辑。供 CLI 和 GUI 共用。

    回调:
      on_progress(jpg, row, done, total)  — 每张完成时触发
      on_log(message)                     — 状态消息(开始/完成/错误)
      stop_flag()                         — 返回 True 时请求停止(完成当前后退出)

    返回:
      {
        "csv_path": Path | None,
        "total": int,           # 目录总 JPG 数
        "processed": int,       # 已完成的新处理数
        "skipped": int,         # 本次因已处理而跳过的数
        "failed": int,          # 有 error 的行数
        "fatal": Optional[str], # llama-server 宕机等致命错误
        "interrupted": bool,    # 是否被 stop_flag 中断
      }
    """
    log = on_log or (lambda msg: print(msg))
    progress = on_progress or (lambda *a, **k: None)
    should_stop = stop_flag or (lambda: _interrupted)

    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"目录不存在: {folder}")

    pairs = scan_folder(folder)
    if not pairs:
        log(f"目录中没有图片文件: {folder}")
        return {"csv_path": None, "total": 0, "processed": 0, "skipped": 0,
                "failed": 0, "fatal": None, "interrupted": False}

    existing_csv, processed_set = (None, set())
    if skip_processed:
        existing_csv, processed_set = load_processed(folder)

    todo = [p for p in pairs if p[0].name not in processed_set]
    if limit > 0:
        todo = todo[:limit]

    log(f"目录: {folder}")
    log(f"JPG 总数: {len(pairs)}  已处理: {len(processed_set)}  待处理: {len(todo)}")
    metadata_mode = metadata_mode if metadata_mode in {"embed", "sidecar"} else METADATA_MODE
    meta_desc = "否" if not write_meta else ("只写 sidecar" if metadata_mode == "sidecar" else "嵌入 JPG/PNG + RAW sidecar")
    log(f"写 XMP 元数据: {meta_desc}")
    if existing_csv:
        log(f"续写 CSV: {existing_csv.name}")

    if not todo:
        log("没有需要处理的照片。")
        return {"csv_path": existing_csv, "total": len(pairs), "processed": 0,
                "skipped": len(processed_set), "failed": 0, "fatal": None,
                "interrupted": False}

    if existing_csv:
        csv_path = existing_csv
        file_mode = "a"
        write_header = False
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label_part = f"_{prompt_label}" if prompt_label else ""
        csv_path = folder / f"triage_{stamp}{label_part}.csv"
        file_mode = "w"
        write_header = True

    conc = max(1, concurrency)
    if conc > 1:
        log(f"并发数: {conc}  (需服务端 --parallel ≥ {conc})")

    csv_lock = threading.Lock()
    fatal_holder: dict[str, Optional[str]] = {"error": None}
    fatal_lock = threading.Lock()
    counters = {"done": 0, "failed": 0}

    def process_one(jpg: Path, raw: Optional[Path]) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            kwargs: dict[str, Any] = {"prompt": prompt, "api_url": api_url}
            if base_url:
                kwargs["base_url"] = base_url
            if model:
                kwargs["model"] = model
            if api_key:
                kwargs["api_key"] = api_key
            if provider_type:
                kwargs["provider_type"] = provider_type
            result = analyze_image(jpg, **kwargs)
        except RuntimeError as e:
            with fatal_lock:
                if fatal_holder["error"] is None:
                    fatal_holder["error"] = str(e)
            return {"_row": result_to_row(jpg, raw, {"_error": str(e)}, 0.0),
                    "_fatal": True}
        elapsed = time.monotonic() - t0
        row = result_to_row(jpg, raw, result, elapsed)

        if write_meta and not row["错误"]:
            try:
                meta = build_metadata(result)
                xmp = build_xmp(meta)
                if metadata_mode == "sidecar":
                    write_xmp_sidecar(jpg, xmp)
                    if raw:
                        write_xmp_sidecar(raw, xmp)
                else:
                    embed_xmp(jpg, xmp)
                    if raw:
                        write_xmp_sidecar(raw, xmp)
            except Exception as e:  # noqa: BLE001
                log(f"[!] 写入元数据失败 {jpg.name}: {e}")

        return {"_row": row, "_fatal": False}

    total_new = len(todo)
    with csv_path.open(file_mode, encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
            fh.flush()

        def commit(jpg: Path, raw: Optional[Path], row: dict) -> None:
            with csv_lock:
                writer.writerow(row)
                fh.flush()
            counters["done"] += 1
            if row.get("错误"):
                counters["failed"] += 1
            progress(jpg, row, counters["done"], total_new)

        if conc == 1:
            for jpg, raw in todo:
                if should_stop() or fatal_holder["error"]:
                    break
                out = process_one(jpg, raw)
                commit(jpg, raw, out["_row"])
                if out["_fatal"]:
                    break
        else:
            pending_items = iter(todo)
            pool = ThreadPoolExecutor(max_workers=conc)

            def submit_next(active: dict) -> bool:
                if should_stop() or fatal_holder["error"]:
                    return False
                try:
                    jpg, raw = next(pending_items)
                except StopIteration:
                    return False
                active[pool.submit(process_one, jpg, raw)] = (jpg, raw)
                return True

            active: dict = {}
            try:
                for _ in range(conc):
                    if not submit_next(active):
                        break
                while active:
                    done, _ = wait(active, return_when=FIRST_COMPLETED)
                    for fut in done:
                        jpg, raw = active.pop(fut)
                        try:
                            out = fut.result()
                        except Exception as e:  # noqa: BLE001
                            log(f"[!] {jpg.name}: {e}")
                            counters["done"] += 1
                            counters["failed"] += 1
                            progress(jpg, {"错误": str(e), "JPG文件名": jpg.name},
                                     counters["done"], total_new)
                        else:
                            commit(jpg, raw, out["_row"])
                            if out["_fatal"]:
                                with fatal_lock:
                                    fatal_holder["error"] = fatal_holder["error"] or "致命错误"
                        if not (should_stop() or fatal_holder["error"]):
                            submit_next(active)
                    if should_stop() or fatal_holder["error"]:
                        break
            except KeyboardInterrupt:
                pass
            finally:
                # 只保持 concurrency 个任务在飞。停止时不会继续提交整批剩余照片。
                pool.shutdown(wait=True, cancel_futures=True)

    return {
        "csv_path": csv_path,
        "total": len(pairs),
        "processed": counters["done"],
        "skipped": len(processed_set),
        "failed": counters["failed"],
        "fatal": fatal_holder["error"],
        "interrupted": should_stop(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="照片批量初筛")
    parser.add_argument("--folder", default=PHOTO_FOLDER, help="照片目录")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 张(0=全部)")
    parser.add_argument("--no-metadata", action="store_true", help="不写 XMP 元数据")
    parser.add_argument("--metadata-mode", choices=("embed", "sidecar"), default=METADATA_MODE,
                        help="embed=嵌入 JPG/PNG 并给 RAW 写 sidecar; sidecar=只生成 .xmp sidecar")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY,
                        help=f"并发数(需 ≤ llama-server --parallel,默认 {CONCURRENCY})")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"错误: 目录不存在 {folder}", file=sys.stderr)
        return 1

    write_meta = WRITE_METADATA and not args.no_metadata

    # 连接预检
    ok, info = check_server()
    if not ok:
        print(f"无法连接 llama-server: {info}", file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, _sigint_handler)

    # CLI: 用 tqdm 做进度 + print 做日志
    pbar: dict[str, Any] = {"obj": None}

    def on_log(msg: str) -> None:
        if pbar["obj"]:
            pbar["obj"].write(msg)
        else:
            print(msg)

    def on_progress(jpg: Path, row: dict, done: int, total: int) -> None:
        if pbar["obj"] is None:
            pbar["obj"] = tqdm(total=total, desc="分析中", unit="img")
        pbar["obj"].update(1)
        pbar["obj"].write(
            f"  {jpg.name} | 综合 {row.get('综合评分', '')} | "
            f"{row.get('场景', '')} | "
            f"{row.get('主体') or row.get('错误') or '(无)'}"
        )

    try:
        result = run_batch(
            folder=folder,
            concurrency=args.concurrency,
            write_meta=write_meta,
            metadata_mode=args.metadata_mode,
            limit=args.limit,
            on_progress=on_progress,
            on_log=on_log,
        )
    finally:
        if pbar["obj"]:
            pbar["obj"].close()

    if result["fatal"]:
        print(f"\n{result['fatal']}", file=sys.stderr)
        print(f"已保存部分结果。CSV: {result['csv_path']}", file=sys.stderr)
        return 2

    if result["csv_path"]:
        print(f"\n完成。CSV: {result['csv_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
