bl_info = {
    "name": "AI World Builder",
    "author": "云袖 & 终",
    "version": (0, 12, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > World Builder",
    "description": "将 Blender 场景转换为 AI 可理解的世界数据库",
    "type": "3D View",
}

"""
AI World Builder - Blender Plugin
=================================
将 Blender 场景转换为 AI 可理解的世界数据库。
"""

import bpy
import json
import math
import mathutils
import os
import sys
import uuid
from bpy.props import (
    StringProperty,
    EnumProperty,
    CollectionProperty,
    BoolProperty,
    IntProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    UIList,
)

# 导入统一的 Observation 引擎
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# =============================================================================
# Constants
# =============================================================================

VERSION = "0.12.0"

class AWB_PT_WorldManagementPanel(Panel):
    """World Management — 世界高级管理（默认折叠）"""
    bl_label = "🛠 World Management"
    bl_idname = "AWB_PT_WorldManagementPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "World Builder"
    bl_order = 5

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        is_expanded = scene.awb_show_advanced
        icon = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT"

        row = layout.row(align=True)
        row.prop(scene, "awb_show_advanced", text="", icon=icon, emboss=False)
        row.label(text="高级管理", icon="TOOL_SETTINGS")

        if not is_expanded:
            return

        # ── Region Topology ──
        layout.separator()
        box = layout.box()
        box.label(text="🏠 Region Topology", icon="WORLD")
        self._draw_regions(box, scene)

        # ── Object Relations ──
        layout.separator()
        self._draw_relations(layout, context, scene)



    def _draw_regions(self, layout, scene):
        from io import StringIO
        # 新增/删除区域
        row = layout.row(align=True)
        row.prop(scene, "awb_new_region_name", text="")
        row.operator("awb.add_region", text="+", icon="ADD")

        # 列出已有区域
        regions_raw = getattr(scene, "awb_regions", "[]")
        try:
            regions = json.loads(regions_raw)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            regions = []

        if regions:
            col = layout.column(align=True)
            for i, r in enumerate(regions):
                if isinstance(r, dict):
                    name = r.get("name", f"Region {i}")
                else:
                    name = str(r)
                row = col.row(align=True)
                row.label(text=f"  {name}", icon="DOT")
                op = row.operator("awb.remove_region", text="", icon="X")
                op.region_index = i

        # 连接区域
        if len(regions) >= 2:
            layout.separator()
            box = layout.box()
            box.label(text="↔ 连接区域", icon="LINKED")

            a_idx = scene.awb_conn_idx_a

            # 所有区域按钮
            for i, r in enumerate(regions):
                name = r.get("name", "?") if isinstance(r, dict) else str(r)
                is_selected = (i == a_idx)

                if is_selected:
                    # 已选中：灰显，点击取消
                    row = box.row(align=True)
                    row.label(text=f"{name}", icon="RADIOBUT_ON")
                    op = row.operator("awb.pick_conn_region", text="✕ 取消", icon="X")
                    op.index = -1
                elif a_idx >= 0:
                    # 第二个：直接连接
                    row = box.row(align=True)
                    row.label(text=f"{name}", icon="RADIOBUT_OFF")
                    op = row.operator("awb.connect_regions", text="→ 连接", icon="LINKED")
                    op.index = i
                else:
                    # 第一个：选择
                    row = box.row(align=True)
                    row.label(text=f"{name}", icon="RADIOBUT_OFF")
                    op = row.operator("awb.pick_conn_region", text="选择", icon="RADIOBUT_ON")
                    op.index = i

            # 已有连接 + 断开
            connections = []
            for i, r in enumerate(regions):
                name = r.get("name", "") if isinstance(r, dict) else str(r)
                for conn in r.get("connections", []):
                    if name < conn:
                        connections.append((name, conn, i))
            if connections:
                layout.separator()
                box = layout.box()
                box.label(text="已连接", icon="LINKED")
                col = box.column(align=True)
                for src_name, dst_name, src_idx in connections:
                    row = col.row(align=True)
                    row.label(text=f"{src_name} ↔ {dst_name}", icon="DOT")
                    op = row.operator("awb.disconnect_regions", text="", icon="X")
                    op.src_name = src_name
                    op.dst_name = dst_name

    def _draw_relations(self, layout, context, scene):
        relations = _load_relations()

        box = layout.box()
        box.label(text="🔗 Object Relations", icon="LINKED")

        if relations:
            col = box.column(align=True)
            for i, rel in enumerate(relations):
                a = rel.get("source", rel.get("from", "?"))
                b = rel.get("target", rel.get("to", "?"))
                t = rel.get("type", "?")
                # 尝试把物体ID映射为标签名
                a_label = _resolve_label(a) or a
                b_label = _resolve_label(b) or b
                row = col.row(align=True)
                row.label(text=f"{a_label} → {b_label} ({t})")
                op = row.operator("awb.remove_relation", text="", icon="X")
                op.rel_index = i

        # 快速关系
        selected = [o for o in context.selected_objects if has_annotation(o) and getattr(o, "awb_id", "")]
        if len(selected) == 2:
            row = box.row(align=True)
            op = row.operator("awb.quick_relation", text="on →", icon="LINKED")
            op.rel_type = "on"
            op = row.operator("awb.quick_relation", text="in →", icon="LINKED")
            op.rel_type = "inside"
            op = row.operator("awb.quick_relation", text="above →", icon="LINKED")
            op.rel_type = "above"
        else:
            if not relations:
                box.label(text="选中 2 个已标注物体建立关系", icon="INFO")




# =============================================================================
# Helpers
# =============================================================================


def _resolve_label(obj_id: str) -> str:
    """根据 awb_id 查找物体标签名"""
    for obj in bpy.context.scene.objects:
        if getattr(obj, "awb_id", "") == obj_id:
            label = getattr(obj, "awb_label", "")
            return label or obj.name
    return ""


import os
import sys
import uuid
from bpy.props import (
    StringProperty,
    EnumProperty,
    CollectionProperty,
    BoolProperty,
    IntProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    UIList,
)

# 导入统一的 Observation 引擎
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from world_db import WorldDB
# 强制重载 observation_builder（Blender 缓存 workaround）
import importlib
import observation_builder
importlib.reload(observation_builder)
from observation_builder import observe, format_observation_text

# =============================================================================
# Constants
# =============================================================================

VERSION = "0.12.0"

TYPE_ENUM = [
    ("unclassified", "未分类", "尚未标注，不会被导出"),
    ("furniture", "家具", "家具：椅子、桌子、床等"),
    ("container", "容器", "容器：箱子、抽屉、冰箱等"),
    ("door", "门/通道", "门、入口、拱门"),
    ("item", "小物品", "钥匙、杯子、书等"),
    ("character", "角色/NPC", "角色站位"),
    ("structure", "建筑结构", "墙、柱、地板、天花板"),
    ("nature", "自然物", "树、草、石头、花、水"),
    ("light", "光源", "灯、火把等"),
    ("region", "区域标记", "房间边界、触发区"),
    ("misc", "其他", "无法归入以上分类"),
]

# 自定义属性 ID，用于检测物体是否已标注（非 UUID 的备用标记）
AWB_ID_KEY = "awb_id"


# =============================================================================
# Helpers
# =============================================================================

def has_annotation(obj):
    """检查物体是否已标注（category 不等于 unclassified 即视为已标注）"""
    cat = getattr(obj, "awb_type", "unclassified")
    return cat and cat != "unclassified"


def _collect_stats(objects_data, scene_objects):
    """生成导出统计信息"""
    total_mesh = sum(1 for o in scene_objects if o.type == "MESH")
    unlabeled_mesh = sum(1 for o in scene_objects if o.type == "MESH" and not has_annotation(o))

    by_category = {}
    by_region = {}
    for obj in objects_data:
        cat = obj.get("type", "")
        by_category[cat] = by_category.get(cat, 0) + 1
        reg = obj.get("region", "")
        by_region[reg or "(未设区域)"] = by_region.get(reg or "(未设区域)", 0) + 1

    return {
        "exported_objects": len(objects_data),
        "total_mesh": total_mesh,
        "unlabeled_mesh": unlabeled_mesh,
        "by_category": by_category,
        "by_region": by_region,
    }


# ══════════════════════════════════════════════════════════════════════
# v0.8 智能语义推断规则
# 结构: { "keyword": { category?, tags?, interactions? } }
# 每条规则可选 category / tags / interactions 中的一个或多个
# 多个关键词同时命中时取所有推断结果的并集
# 规则顺序无关（统一收集所有匹配后合并），长词短词均可
# ══════════════════════════════════════════════════════════════════════

_AUTO_RULES = {
    # ── furniture ──
    "椅子": {"type": "furniture", "flags": ["可移动"], "actions": ["坐"]},
    "凳子": {"type": "furniture", "flags": ["可移动"], "actions": ["坐"]},
    "沙发": {"type": "furniture", "flags": ["可移动", "柔软"], "actions": ["坐"]},
    "桌子": {"type": "furniture", "flags": ["固定"], "actions": ["检查"]},
    "床":   {"type": "furniture", "flags": ["柔软"], "actions": ["躺下", "坐"]},
    "柜子": {"type": "furniture", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "书架": {"type": "furniture", "flags": ["固定"], "actions": ["检查", "拾取"]},
    "架":   {"type": "furniture", "flags": ["固定"], "actions": ["检查"]},
    "椅":   {"type": "furniture", "flags": ["可移动"], "actions": ["坐"]},
    "凳":   {"type": "furniture", "flags": ["可移动"], "actions": ["坐"]},
    "桌":   {"type": "furniture", "flags": ["固定"], "actions": ["检查"]},
    "柜":   {"type": "furniture", "flags": ["可移动"], "actions": ["打开"]},
    "chair":  {"type": "furniture", "flags": ["可移动"], "actions": ["坐"]},
    "sofa":   {"type": "furniture", "flags": ["可移动", "柔软"], "actions": ["坐"]},
    "couch":  {"type": "furniture", "flags": ["可移动", "柔软"], "actions": ["坐"]},
    "table":  {"type": "furniture", "flags": ["固定"], "actions": ["检查"]},
    "desk":   {"type": "furniture", "flags": ["固定"], "actions": ["检查"]},
    "bed":    {"type": "furniture", "flags": ["柔软"], "actions": ["躺下", "坐"]},
    "shelf":  {"type": "furniture", "flags": ["固定"], "actions": ["检查", "拾取"]},
    "cabinet": {"type": "furniture", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "书柜": {"type": "furniture", "actions": ["打开", "检查"]},
    "bookcase": {"type": "furniture", "actions": ["检查", "拾取"]},
    "pillow": {"type": "furniture", "flags": ["柔软"], "actions": ["拾取"]},
    "枕头": {"type": "furniture", "flags": ["柔软"], "actions": ["拾取"]},
    "rug": {"type": "furniture", "actions": ["检查"]},
    "地毯": {"type": "furniture", "actions": ["检查"]},
    "curtain": {"type": "furniture", "flags": ["布料"], "actions": ["开关"]},
    "窗帘": {"type": "furniture", "flags": ["布料"], "actions": ["开关"]},

    # ── container ──
    "箱子": {"type": "container", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "抽屉": {"type": "container", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "箱":   {"type": "container", "actions": ["打开"]},
    "chest":  {"type": "container", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "drawer": {"type": "container", "flags": ["可移动"], "actions": ["打开", "检查"]},
    "box":    {"type": "container", "actions": ["打开"]},
    "container": {"type": "container", "actions": ["打开"]},

    # ── door ──
    "门":   {"type": "door", "flags": ["遮挡视线"], "actions": ["开门", "关门"]},
    "入口": {"type": "door", "actions": ["开门", "关门"]},
    "door": {"type": "door", "flags": ["遮挡视线"], "actions": ["开门", "关门"]},
    "gate": {"type": "door", "actions": ["开门", "关门"]},

    # ── item ──
    "钥匙": {"type": "item", "flags": ["金属"], "actions": ["拾取", "使用"]},
    "书":   {"type": "item", "actions": ["拾取", "阅读"]},
    "杯":   {"type": "item", "flags": ["易碎", "陶瓷"], "actions": ["拾取", "使用"]},
    "key":  {"type": "item", "flags": ["金属"], "actions": ["拾取", "使用"]},
    "book": {"type": "item", "actions": ["拾取", "阅读"]},
    "cup":  {"type": "item", "flags": ["易碎"], "actions": ["拾取", "使用"]},
    "bottle": {"type": "item", "flags": ["玻璃"], "actions": ["拾取", "使用"]},
    "瓶":    {"type": "item", "flags": ["玻璃"], "actions": ["拾取", "使用"]},

    # ── light ──
    "灯":   {"type": "light", "flags": ["发光"], "actions": ["开关"]},
    "火把": {"type": "light", "flags": ["发光", "可燃"], "actions": ["开关", "点燃", "熄灭"]},
    "light": {"type": "light", "flags": ["发光"], "actions": ["开关"]},
    "lamp":  {"type": "light", "flags": ["发光"], "actions": ["开关"]},
    "candle": {"type": "light", "flags": ["发光", "可燃"], "actions": ["点燃", "熄灭"]},
    "蜡烛":  {"type": "light", "flags": ["发光", "可燃"], "actions": ["点燃", "熄灭"]},

    # ── nature ──
    "树":   {"type": "nature", "flags": ["可燃"], "actions": ["检查"]},
    "草":   {"type": "nature", "actions": ["检查"]},
    "花":   {"type": "nature", "flags": ["易碎"], "actions": ["拾取", "检查"]},
    "岩石": {"type": "nature", "flags": ["固定"], "actions": ["检查"]},
    "石":   {"type": "nature", "actions": ["检查"]},
    "tree":   {"type": "nature", "flags": ["可燃"], "actions": ["检查"]},
    "grass":  {"type": "nature", "actions": ["检查"]},
    "flower": {"type": "nature", "flags": ["易碎"], "actions": ["拾取", "检查"]},
    "stone":  {"type": "nature", "flags": ["固定"], "actions": ["检查"]},
    "rock":   {"type": "nature", "flags": ["固定"], "actions": ["检查"]},

    # ── structure ──
    "墙":   {"type": "structure", "flags": ["固定", "遮挡视线"], "actions": []},
    "柱":   {"type": "structure", "flags": ["固定"], "actions": ["检查"]},
    "柱子": {"type": "structure", "flags": ["固定"], "actions": ["检查"]},
    "地板": {"type": "structure", "flags": ["固定"], "actions": []},
    "天花板": {"type": "structure", "flags": ["固定"], "actions": []},
    "wall":   {"type": "structure", "flags": ["固定", "遮挡视线"], "actions": []},
    "floor":  {"type": "structure", "flags": ["固定"], "actions": []},
    "ceiling": {"type": "structure", "flags": ["固定"], "actions": []},
    "pillar":  {"type": "structure", "flags": ["固定"], "actions": ["检查"]},

    # ── character ──
    "角色": {"type": "character", "actions": ["对话"]},
    "人":   {"type": "character", "actions": ["对话"]},
    "character": {"type": "character", "actions": ["对话"]},
    "npc":      {"type": "character", "actions": ["对话"]},

    # ── region ──
    "区域": {"type": "region", "actions": []},
    "region": {"type": "region", "actions": []},

    # ── 材质/特征标签（只加 tags，不改 category）──
    "wood":  {"flags": ["木质"]},
    "木":    {"flags": ["木质"]},
    "metal": {"flags": ["金属"]},
    "铁":    {"flags": ["金属"]},
    "钢":    {"flags": ["金属"]},
    "金":    {"flags": ["金属"]},
    "glass": {"flags": ["玻璃", "易碎"]},
    "玻璃":  {"flags": ["玻璃", "易碎"]},
    "cloth": {"flags": ["布料", "柔软"]},
    "布":    {"flags": ["布料", "柔软"]},
    "leather": {"flags": ["皮革"]},
    "皮革":   {"flags": ["皮革"]},
}


def auto_classify(obj_name: str) -> str | None:
    """根据物体名字关键词自动推断 category，匹配不到返回 None。
    保留了兼容旧版（AutoSetType 用），内部调用 infer_annotation。"""
    result = infer_annotation(obj_name)
    return result.get("type")


def infer_annotation(obj_name: str) -> dict:
    """根据物体名称进行语义推断。

    返回:
    {
        "type": str | None,       # 推断的分类，None 表示未匹配到
        "flags": [str],                # 推断的标签
        "actions": [str],        # 推断的交互行为
        "confidence": float,          # 置信度 0~1（基于匹配到的规则数量和权重）
        "matched": [str],             # 命中的关键词列表
    }

    当多个关键词同时命中时：
    - category 取最长命中的关键词（更长 = 更精确）
    - tags 和 interactions 取所有匹配到的并集
    例如 "Bookcase_Wood" → "bookcase"(5字) > "book"(4字母) → furniture
                      → "wood" 追加 tags=[木质]
    """
    name_lower = obj_name.lower()

    # 按关键词长度降序遍历：长词优先匹配
    sorted_keywords = sorted(_AUTO_RULES.keys(), key=len, reverse=True)

    matched = []
    cat = None
    cat_key_len = 0  # 当前 category 对应的关键词长度
    tags = []
    interactions = []

    for keyword in sorted_keywords:
        if keyword in name_lower:
            matched.append(keyword)
            rule = _AUTO_RULES[keyword]
            # category: 取最长命中
            if rule.get("type") and len(keyword) > cat_key_len:
                cat = rule["type"]
                cat_key_len = len(keyword)
            for t in rule.get("flags", []):
                if t not in tags:
                    tags.append(t)
            for i in rule.get("actions", []):
                if i not in interactions:
                    interactions.append(i)

    # confidence 计算：有 category 匹配 + 匹配数量加权
    if not matched:
        return {
            "type": None,
            "flags": [],
            "actions": [],
            "confidence": 0.0,
            "matched": [],
        }

    # 基础分：有 category 匹配 = 0.5，没有 = 0.1
    base = 0.5 if cat else 0.1
    # 加权：每多一个匹配词 +0.1
    bonus = min(0.5, len(matched) * 0.1)
    confidence = round(base + bonus, 2)

    return {
        "type": cat,
        "flags": tags,
        "actions": interactions,
        "confidence": confidence,
        "matched": matched,
    }


# =============================================================================
# Helpers (presets)
# =============================================================================

def _get_category_filter_items(context):
    """构建分类筛选下拉：收集场景中所有分类"""
    try:
        items = [("", "全部", "")]
        seen = set()
        for obj in context.scene.objects:
            if not has_annotation(obj):
                continue
            cat = getattr(obj, "awb_type", "")
            # 只接受合法分类键
            if cat and cat not in seen and cat != "unclassified" and cat in [k for k, _, _ in TYPE_ENUM]:
                seen.add(cat)
                # 查找中文名
                label = cat
                for key, name, _ in TYPE_ENUM:
                    if key == cat:
                        label = name
                        break
                items.append((cat, label, ""))
        return items
    except Exception:
        return [("", "全部", "")]

def _get_tag_filter_items(context):
    """构建标签筛选下拉：收集场景中所有标签"""
    try:
        items = [("", "全部", "")]
        seen = set()
        for obj in context.scene.objects:
            if not has_annotation(obj):
                continue
            tags_val = getattr(obj, "awb_flags", "")
            if tags_val and len(tags_val) <= 100:
                for t in tags_val.split(","):
                    t = t.strip()
                    if not t or t in seen:
                        continue
                    # 标签过滤：必须有意义
                    ok = False
                    try:
                        t.encode("ascii")
                        # 纯英文标签 — 接受（如 food, wooden）
                        if len(t) >= 3:
                            ok = True
                    except UnicodeEncodeError:
                        # 非 ASCII — 必须含中文才接受
                        if any(0x4E00 <= ord(c) <= 0x9FFF for c in t):
                            ok = True
                    if ok:
                        seen.add(t)
                        items.append((t, t, ""))
        return items
    except Exception:
        return [("", "全部", "")]

def _get_search_region_items(context):
    """构建区域搜索下拉：列出所有已注册区域"""
    import json
    try:
        items = [("", "全部", "")]
        regions_raw = getattr(context.scene, "awb_regions", "")
        if regions_raw and isinstance(regions_raw, str):
            try:
                regions = json.loads(regions_raw)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                regions = []
            for r in regions:
                if isinstance(r, dict):
                    name = r.get("name", "")
                else:
                    name = str(r)
                # 过滤明显的脏数据
                if name and isinstance(name, str) and len(name) >= 2 and len(name) <= 100:
                    try:
                        name.encode("ascii")
                        # 纯 ASCII 也可以（如 bedroom）
                        items.append((name, name, ""))
                    except UnicodeEncodeError:
                        # 非 ASCII — 检查是否全是可打印字符
                        if all(ord(c) >= 0x4E00 or ord(c) >= 32 for c in name) and not any(c in name for c in "\x00\x01\x02"):
                            items.append((name, name, ""))
        seen = set()
        for obj in context.scene.objects:
            if not has_annotation(obj):
                continue
            r = getattr(obj, "awb_region", "")
            # 过滤乱码：区域名必须是中文或合理英文
            if r and r not in seen and len(r) >= 2:
                try:
                    r.encode("ascii")
                    # 纯 ASCII → 也允许（如 bedroom）
                    seen.add(r)
                    items.append((r, r, ""))
                except UnicodeEncodeError:
                    # 非 ASCII → 必须含 CJK 字符才认为是有效中文区域名
                    if any(0x4E00 <= ord(c) <= 0x9FFF for c in r):
                        seen.add(r)
                        items.append((r, r, ""))
        return items
    except Exception:
        return [("", "全部", "")]

_PRESET_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "presets.json"
)

_DEFAULT_PRESETS = {
    "flags": ["木质", "金属", "玻璃", "塑料", "布料", "石材",
              "食物", "液体", "电子", "纸质", "可移动", "固定",
              "易碎", "可燃", "珍贵", "垃圾"],
    "actions": ["检查", "拾取", "使用", "打开", "关闭",
                      "推动", "破坏", "对话", "阅读", "坐",
                      "割", "弹", "解锁", "放下", "给予"],
}

def _load_presets():
    """加载预设标签和交互"""
    try:
        if os.path.exists(_PRESET_PATH):
            with open(_PRESET_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(_DEFAULT_PRESETS)
                merged.update(data)
                return merged
    except (json.JSONDecodeError, IOError):
        pass
    return dict(_DEFAULT_PRESETS)

_awb_data_path = None  # 缓存，避免每次读 bpy.data

def _get_data_path():
    """获取当前 blend 文件同目录下的持久化路径"""
    global _awb_data_path
    if _awb_data_path is not None:
        return _awb_data_path
    try:
        path = bpy.data.filepath
        if path:
            _awb_data_path = os.path.splitext(path)[0] + ".awb_world_data.json"
    except Exception:
        pass
    return _awb_data_path


def _save_all_to_file():
    """保存区域 + 关系到 blend 文件旁"""
    data_path = _get_data_path()
    if not data_path:
        return
    try:
        scene = bpy.context.scene
        raw_regions = getattr(scene, "awb_regions", "[]")
        raw_relations = getattr(scene, "awb_relations", "[]")
        data = {
            "regions": json.loads(raw_regions) if isinstance(raw_regions, str) else [],
            "relations": json.loads(raw_relations) if isinstance(raw_relations, str) else [],
        }
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 未保存或不支持上下文


def _load_all_from_file():
    """从 blend 文件旁恢复区域 + 关系"""
    data_path = _get_data_path()
    if not data_path or not os.path.exists(data_path):
        return
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        regions = data.get("regions", [])
        relations = data.get("relations", [])
        scene = bpy.context.scene
        if regions:
            scene.awb_regions = json.dumps(regions, ensure_ascii=False)
        if relations:
            scene.awb_relations = json.dumps(relations, ensure_ascii=False)
        print(f"[AWB] 从 {data_path} 恢复 {len(regions)} 区域, {len(relations)} 条关系")
    except Exception as e:
        print(f"[AWB] 恢复失败: {e}")


def _load_regions():
    """从 Scene 属性加载区域拓扑"""
    raw = getattr(bpy.context.scene, "awb_regions", "")
    if raw and isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            pass
    return []

def _save_regions(regions: list):
    """保存区域拓扑到 Scene 属性 + 文件"""
    bpy.context.scene.awb_regions = json.dumps(regions, ensure_ascii=False)
    _save_all_to_file()

def _load_relations():
    """从 Scene 属性加载关系列表"""
    raw = getattr(bpy.context.scene, "awb_relations", "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return []

def _save_relations(relations: list):
    """保存关系列表到 Scene 属性 + 文件"""
    bpy.context.scene.awb_relations = json.dumps(relations, ensure_ascii=False)
    _save_all_to_file()


# =============================================================================
# Operators
# =============================================================================

class AWB_OT_ExportWorld(Operator):
    """导出 world.json"""
    bl_idname = "awb.export_world"
    bl_label = "导出 world.json"
    bl_description = "将场景中所有已标注物体导出为世界数据库"

    filepath: StringProperty(subtype="FILE_PATH")  # type: ignore

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        filepath = self.filepath
        if not filepath.endswith(".json"):
            filepath += ".json"

        objects_data = []
        obj_index = 0

        for obj in bpy.context.scene.objects:
            if not has_annotation(obj):
                continue

            obj_index += 1
            obj_data = self._extract_object(obj, obj_index)
            objects_data.append(obj_data)

        stats = _collect_stats(objects_data, bpy.context.scene.objects)

        world_data = {
            "version": VERSION,
            "scene_name": bpy.context.scene.name,
            "regions": _collect_regions(),
            "objects": objects_data,
            "relations": _load_relations(),
            "metadata": {
                "export_time": self._get_iso_time(),
                "unit": "meters",
                "stats": stats,
            },
        }

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        # ── 导出前验证 ──
        tmp_path = filepath + ".validate_tmp.json"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(world_data, f, ensure_ascii=False)
        try:
            db = WorldDB(tmp_path)
            v = db.validate()
            if v["errors"]:
                err_lines = [f"  [{e['code']}] {e['message']}" for e in v["errors"]]
                warn_lines = [f"  [WARN {w['code']}] {w['message']}" for w in v["warnings"]]
                msg = "导出验证失败:\n" + "\n".join(err_lines + warn_lines)
                self.report({"ERROR"}, f"{v['summary']} — 见系统控制台")
                print(f"\n{'='*50}")
                print(f"⚠️  世界验证失败: {v['summary']}")
                print(f"{'='*50}")
                for e in v["errors"]:
                    print(f"  ❌ [{e['code']}] {e['message']}")
                    print(f"     {e['detail']}")
                for w in v["warnings"]:
                    print(f"  ⚠️  [{w['code']}] {w['message']}")
                    print(f"     {w['detail']}")
                print(f"{'='*50}")
                print("文件仍然已写入，但建议修复以上问题后重新导出。\n")
            elif v["warnings"]:
                self.report({"WARNING"}, f"{v['summary']} — 见系统控制台")
                print(f"\n⚠️  世界验证有警告: {v['summary']}")
                for w in v["warnings"]:
                    print(f"  [{w['code']}] {w['message']}")
                    print(f"     {w['detail']}")
            else:
                self.report({"INFO"}, "✅ 验证通过")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(world_data, f, ensure_ascii=False, indent=2)

        self.report({"INFO"}, f"导出完成: {len(objects_data)} 个物体 → {filepath}")
        return {"FINISHED"}

    def _extract_object(self, obj, index):
        """提取单个物体的标注数据"""
        # 包围盒 — 兼容 Blender 4.x (v.co) 和 5.x (直接下标)
        bbox_corners = []
        for v in obj.bound_box:
            if hasattr(v, "co"):
                bbox_corners.append(obj.matrix_world @ v.co)
            else:
                bbox_corners.append(obj.matrix_world @ mathutils.Vector(v))
        xs = [v.x for v in bbox_corners]
        ys = [v.y for v in bbox_corners]
        zs = [v.z for v in bbox_corners]

        # 解析 tags（逗号分隔存储）
        tags_raw = getattr(obj, "awb_flags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        # 解析 interactions
        interactions_raw = getattr(obj, "awb_actions", "")
        interactions = [t.strip() for t in interactions_raw.split(",") if t.strip()]

        # 解析 properties（JSON 字符串存储）
        props_raw = getattr(obj, "awb_properties", "{}")
        try:
            properties = json.loads(props_raw)
        except json.JSONDecodeError:
            properties = {}

        # 解析 parent
        parent_id = None
        if obj.parent and has_annotation(obj.parent):
            parent_id = getattr(obj.parent, "awb_id", None)

        return {
            "id": getattr(obj, "awb_id", f"obj_{index:03d}"),
            "blender_name": obj.name,
            "label": getattr(obj, "awb_label", "") or obj.name,
            "type": getattr(obj, "awb_type", "misc"),
            "flags": tags,
            "actions": interactions,
            "parent": parent_id,
            "region": getattr(obj, "awb_region", ""),
            "position": {
                "x": round(obj.location.x, 4),
                "y": round(obj.location.y, 4),
                "z": round(obj.location.z, 4),
            },
            "rotation": {
                "x": round(math.degrees(obj.rotation_euler.x), 4),
                "y": round(math.degrees(obj.rotation_euler.y), 4),
                "z": round(math.degrees(obj.rotation_euler.z), 4),
            },
            "scale": {
                "x": round(obj.scale.x, 4),
                "y": round(obj.scale.y, 4),
                "z": round(obj.scale.z, 4),
            },
            "bbox": {
                "min": {"x": round(min(xs), 4), "y": round(min(ys), 4), "z": round(min(zs), 4)},
                "max": {"x": round(max(xs), 4), "y": round(max(ys), 4), "z": round(max(zs), 4)},
            },
            "properties": properties,
        }

    def _get_iso_time(self):
        import datetime
        return datetime.datetime.now().isoformat()


class AWB_OT_AssignID(Operator):
    """给当前选中物体分配唯一 ID"""
    bl_idname = "awb.assign_id"
    bl_label = "分配 ID"
    bl_description = "给选中物体分配唯一标识"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({"WARNING"}, "请先选中一个物体")
            return {"CANCELLED"}

        if not getattr(obj, "awb_id", ""):
            uid = str(uuid.uuid4())[:8]
            obj.awb_id = uid
            self.report({"INFO"}, f"已分配 ID: {uid}")

        return {"FINISHED"}


class AWB_OT_ClearAnnotation(Operator):
    """清除选中物体的所有标注"""
    bl_idname = "awb.clear_annotation"
    bl_label = "清除标注"
    bl_description = "清除当前物体的所有 AWB 标注数据"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {"CANCELLED"}

        reset_values = {
            "awb_id": "",
            "awb_label": "",
            "awb_region": "",
            "awb_flags": "",
            "awb_actions": "",
            "awb_properties": "{}",
            "awb_type": "unclassified",
        }
        for attr, default_val in reset_values.items():
            if hasattr(bpy.types.Object, attr):
                try:
                    setattr(obj, attr, default_val)
                except (TypeError, ValueError):
                    pass  # EnumProperty 空值时跳过

        self.report({"INFO"}, f"已清除 {obj.name} 的标注")
        return {"FINISHED"}


class AWB_OT_AddFlag(Operator):
    """点击预设标签 → 追加到当前物体的标签框"""
    bl_idname = "awb.add_flag"
    bl_label = "添加标签预设"
    bl_description = "将预设标签追加到当前物体"

    tag: StringProperty()  # type: ignore

    def execute(self, context):
        obj = context.active_object
        if obj:
            existing = getattr(obj, "awb_flags", "")
            tags = [t.strip() for t in existing.split(",") if t.strip()]
            if self.tag not in tags:
                tags.append(self.tag)
                obj.awb_flags = ", ".join(tags)
                self.report({"INFO"}, f"已添加标签: {self.tag}")
            else:
                self.report({"INFO"}, f"标签已存在: {self.tag}")
        return {"FINISHED"}


class AWB_OT_AddAction(Operator):
    """点击预设交互 → 追加到当前物体的交互行为框"""
    bl_idname = "awb.add_action"
    bl_label = "添加交互预设"
    bl_description = "将预设交互行为追加到当前物体"

    interaction: StringProperty()  # type: ignore

    def execute(self, context):
        obj = context.active_object
        if obj:
            existing = getattr(obj, "awb_actions", "")
            interactions = [t.strip() for t in existing.split(",") if t.strip()]
            if self.interaction not in interactions:
                interactions.append(self.interaction)
                obj.awb_actions = ", ".join(interactions)
                self.report({"INFO"}, f"已添加交互: {self.interaction}")
            else:
                self.report({"INFO"}, f"交互已存在: {self.interaction}")
        return {"FINISHED"}


class AWB_OT_AutoSetType(Operator):
    """使用 infer_annotation 自动推理当前物体的 type/flags/actions"""
    bl_idname = "awb.auto_set_type"
    bl_label = "智能推断当前物体"
    bl_description = "根据物体名自动推断 type / flags / actions"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({"WARNING"}, "请先选中一个物体")
            return {"CANCELLED"}

        result = infer_annotation(obj.name)
        if result.get("confidence", 0) == 0:
            self.report({"INFO"}, f"未匹配到规则: {obj.name}")
            return {"FINISHED"}

        overwrite = context.scene.awb_auto_type_overwrite

        if overwrite or not getattr(obj, "awb_type", "unclassified") or getattr(obj, "awb_type", "") == "unclassified":
            if result.get("type"):
                obj.awb_type = result["type"]

        # flags
        if result.get("flags"):
            existing = [f.strip() for f in getattr(obj, "awb_flags", "").split(",") if f.strip()]
            for f in result["flags"]:
                if f not in existing:
                    existing.append(f)
            obj.awb_flags = ", ".join(existing)

        # actions
        if result.get("actions"):
            existing = [a.strip() for a in getattr(obj, "awb_actions", "").split(",") if a.strip()]
            for a in result["actions"]:
                if a not in existing:
                    existing.append(a)
            obj.awb_actions = ", ".join(existing)

        self.report({"INFO"}, f"推断完成: type={result.get('type','?')} conf={result.get('confidence',0)}")
        return {"FINISHED"}


class AWB_OT_CheckUnlabeled(Operator):
    """检查场景中未标注的 mesh 物体"""
    bl_idname = "awb.check_unlabeled"
    bl_label = "检查未标注物体"
    bl_description = "列出场景中所有未标注的 mesh 物体"

    def execute(self, context):
        unlabeled = []
        for obj in bpy.context.scene.objects:
            if obj.type == "MESH" and not has_annotation(obj):
                unlabeled.append(obj.name)

        if unlabeled:
            self.report({"WARNING"}, f"未标注物体: {len(unlabeled)} 个")
            print("\n=== 未标注物体 ===")
            for name in unlabeled:
                print(f"  - {name}")
        else:
            self.report({"INFO"}, "所有 mesh 物体已标注 ✓")

        return {"FINISHED"}



class AWB_OT_RunObservation(Operator):
    """运行 Observation Builder，结果写入面板缓存"""
    bl_idname = "awb.run_observation"
    bl_label = "运行观察"
    bl_description = "以当前坐标和半径执行观察，结果显示在面板中"

    mode: StringProperty(default="scene")  # type: ignore

    def execute(self, context):
        scene = context.scene
        pos = (scene.awb_obs_x, scene.awb_obs_y, scene.awb_obs_z)
        radius = scene.awb_obs_radius

        if self.mode == "file":
            # 由 file selector 触发，已在 invoke 设置了 filepath
            pass

        # 运行引擎始终用统一函数
        objects_data = _collect_annotated_objects()

        # FOV 参数
        dir_x = _safe_float(scene.awb_obs_dir_x)
        dir_y = _safe_float(scene.awb_obs_dir_y)
        dir_z = _safe_float(scene.awb_obs_dir_z)
        fov = _safe_float(scene.awb_obs_fov, 0)
        direction = (dir_x, dir_y, dir_z) if any(v != 0 for v in (dir_x, dir_y, dir_z)) else None
        fov_angle = fov if fov > 0 else None

        observation = observe(objects_data, position=pos, radius=radius,
                              direction=direction, fov_angle=fov_angle)

        # 写入缓存供面板读取
        scene.awb_last_observation = json.dumps(observation, ensure_ascii=False)
        scene.awb_obs_running = False

        n = len(observation["visible_objects"])
        self.report({"INFO"}, f"观察完成: {n} 个可见物体")
        return {"FINISHED"}


class AWB_OT_RunObservationFromFile(Operator):
    """从 world.json 文件运行观察"""
    bl_idname = "awb.run_observation_from_file"
    bl_label = "从 world.json 观察"
    bl_description = "从导出的 world.json 读取物体数据，以当前坐标和半径执行观察"

    filepath: StringProperty(subtype="FILE_PATH")  # type: ignore

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        pos = (context.scene.awb_obs_x, context.scene.awb_obs_y, context.scene.awb_obs_z)
        radius = context.scene.awb_obs_radius

        try:
            db = WorldDB(self.filepath)
            observation = observe(db.objects, position=pos, radius=radius)
            context.scene.awb_last_observation = json.dumps(observation, ensure_ascii=False)

            n = len(observation["visible_objects"])
            self.report({"INFO"}, f"观察完成: {n} 个物体 (来自 file)")
        except Exception as e:
            self.report({"ERROR"}, f"读取 world.json 失败: {e}")

        return {"FINISHED"}


class AWB_OT_ShowObjectDetail(Operator):
    """弹出物体完整信息（从场景实时读取）"""
    bl_idname = "awb.show_detail"
    bl_label = "物体详情"
    bl_description = "显示该物体在世界库中的完整信息"

    obj_id: StringProperty()  # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=360)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        detail = _find_object_by_id(self.obj_id)
        if not detail:
            layout.label(text="未找到该物体", icon="ERROR")
            return

        layout.label(text=f"物体详情", icon="INFO")
        layout.separator()

        # 基本信息
        box = layout.box()
        box.label(text=f"📛 {detail.get('label', '?')}")
        box.label(text=f"ID: {detail.get('id', '?')}")
        box.label(text=f"分类: {detail.get('type', 'misc')}")
        box.label(text=f"区域: {detail.get('region', '') or '(未设置)'}")

        if detail.get("blender_name"):
            box.label(text=f"Blender 名称: {detail['blender_name']}")

        # 位置
        pos = detail.get("position", {})
        if pos:
            box.label(text=f"位置: ({pos.get('x',0):.2f}, {pos.get('y',0):.2f}, {pos.get('z',0):.2f})")

        # 标签
        tags = detail.get("flags", [])
        if tags:
            box.label(text=f"标签: {', '.join(tags)}")

        # 交互
        interactions = detail.get("actions", [])
        if interactions:
            box.label(text=f"可交互: {', '.join(interactions)}")

        # 属性
        props = detail.get("properties", {})
        if props:
            layout.separator()
            layout.label(text="自定义属性:")
            for k, v in props.items() if isinstance(props, dict) else []:
                layout.label(text=f"  {k}: {v}")


# =============================================================================
# Region Operators
# =============================================================================

class AWB_OT_AddRegion(Operator):
    """新增区域"""
    bl_idname = "awb.add_region"
    bl_label = "新增区域"
    bl_description = "在世界拓扑中添加一个新区域"

    def execute(self, context):
        name = context.scene.awb_new_region_name.strip()
        if not name:
            self.report({"ERROR"}, "请输入区域名称")
            return {"CANCELLED"}
        regions = _load_regions()
        # 去重
        for r in regions:
            if r.get("name") == name:
                self.report({"ERROR"}, f"区域「{name}」已存在")
                return {"CANCELLED"}
        # 生成 id
        new_id = f"reg_{len(regions)+1:03d}"
        while any(r.get("id") == new_id for r in regions):
            new_id = f"reg_{len(regions)+1:03d}_{uuid.uuid4().hex[:4]}"
        regions.append({"id": new_id, "name": name, "connections": []})
        _save_regions(regions)
        context.scene.awb_new_region_name = ""
        self.report({"INFO"}, f"已添加区域: {name}")
        return {"FINISHED"}


class AWB_OT_RemoveRegion(Operator):
    """删除区域"""
    bl_idname = "awb.remove_region"
    bl_label = "删除区域"
    bl_description = "从拓扑中删除此区域"

    region_index: IntProperty()  # type: ignore

    def execute(self, context):
        regions = _load_regions()
        idx = self.region_index
        if 0 <= idx < len(regions):
            del regions[idx]
            _save_regions(regions)
            self.report({"INFO"}, f"已删除区域")
        return {"FINISHED"}




class AWB_OT_PickConnRegion(Operator):
    """选择要连接的区域"""
    bl_idname = "awb.pick_conn_region"
    bl_label = "选择区域"
    bl_description = "选择为连接源"

    index: IntProperty(default=-1)  # type: ignore

    def execute(self, context):
        context.scene.awb_conn_idx_a = self.index
        return {"FINISHED"}


class AWB_OT_ConnectRegions(Operator):
    """连接两个区域"""
    bl_idname = "awb.connect_regions"
    bl_label = "连接区域"
    bl_description = "在两个区域之间建立连通关系"

    index: IntProperty(default=-1)  # type: ignore  # 目标区域索引

    def execute(self, context):
        a_idx = context.scene.awb_conn_idx_a
        b_idx = self.index
        if a_idx < 0 or b_idx < 0:
            self.report({"ERROR"}, "请先选择源区域")
            return {"CANCELLED"}
        if a_idx == b_idx:
            self.report({"ERROR"}, "不能连接同一个区域")
            return {"CANCELLED"}
        regions = _load_regions()
        try:
            src_name = regions[a_idx].get("name", "")
            dst_name = regions[b_idx].get("name", "")
        except (IndexError, TypeError):
            self.report({"ERROR"}, "区域数据异常")
            return {"CANCELLED"}
        if not src_name or not dst_name:
            self.report({"ERROR"}, "区域名称异常")
            return {"CANCELLED"}
        # 双向连接
        for idx, other in [(a_idx, dst_name), (b_idx, src_name)]:
            r = regions[idx]
            if other not in r.get("connections", []):
                r.setdefault("connections", []).append(other)
        _save_regions(regions)
        self.report({"INFO"}, f"已连接: {src_name} ↔ {dst_name}")
        # 清除选择
        context.scene.awb_conn_idx_a = -1
        return {"FINISHED"}


class AWB_OT_DisconnectRegions(Operator):
    """断开两个区域的连接"""
    bl_idname = "awb.disconnect_regions"
    bl_label = "断开连接"
    bl_description = "移除两个区域之间的连通关系"

    src_name: StringProperty()  # type: ignore
    dst_name: StringProperty()  # type: ignore

    def execute(self, context):
        src = self.src_name
        dst = self.dst_name
        if not src or not dst:
            self.report({"ERROR"}, "缺少区域信息")
            return {"CANCELLED"}
        regions = _load_regions()
        for r in regions:
            conns = r.get("connections", [])
            if src in conns:
                conns.remove(src)
            if dst in conns:
                conns.remove(dst)
        _save_regions(regions)
        self.report({"INFO"}, f"已断开: {src} ↔ {dst}")
        return {"FINISHED"}


# =============================================================================
# Relation Operators
# =============================================================================

RELATION_TYPES = [
    ("contains", "contains", "A 里面有 B"),
    ("inside", "inside", "B 在 A 里面"),
    ("connects_to", "connects_to", "区域连通"),
    ("unlocks", "unlocks", "解锁"),
    ("activates", "activates", "触发/激活"),
    ("owns", "owns", "归属"),
    ("knows", "knows", "知晓信息"),
    ("uses", "uses", "使用工具"),
    ("related_to", "related_to", "兜底"),
]


class AWB_OT_ValidateWorld(Operator):
    """验证世界完整性"""
    bl_idname = "awb.validate_world"
    bl_label = "验证世界完整性"
    bl_description = "检查 Object ID / Region ID / Relation 引用 / Category 等是否合法"

    def execute(self, context):
        # 在内存中构建临时 world_data
        objects_data = []
        obj_index = 0
        for obj in bpy.context.scene.objects:
            if not has_annotation(obj):
                continue
            obj_index += 1
            oid = getattr(obj, "awb_id", f"obj_{obj_index:03d}")
            loc = obj.location
            objects_data.append({
                "id": oid,
                "label": getattr(obj, "awb_label", "") or obj.name,
                "type": getattr(obj, "awb_type", "misc"),
                "region": getattr(obj, "awb_region", ""),
                "position": {"x": loc.x, "y": loc.y, "z": loc.z},
            })

        world_data = {
            "objects": objects_data,
            "regions": _load_regions(),
            "relations": _load_relations(),
        }

        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(world_data, tmp)
        tmp.close()
        try:
            db = WorldDB(tmp.name)
            v = db.validate()
        finally:
            os.unlink(tmp.name)

        if v["passed"]:
            self.report({"INFO"}, "✅ 验证通过 — 世界完整")
            print(f"\n✅ World Validation Passed — {v['summary']}")
        else:
            # 尝试自动修复 DUPLICATE_OBJECT_ID
            did_heal = False
            for e in v.get("errors", []):
                if e.get("code") == "DUPLICATE_OBJECT_ID":
                    # 从 detail 中提取重复的 id
                    id_dup = e.get("id", "")
                    if id_dup:
                        id_count = {}
                        for obj in context.scene.objects:
                            oid = getattr(obj, "awb_id", "")
                            if oid:
                                id_count.setdefault(oid, []).append(obj)
                        for oid, objs in id_count.items():
                            if len(objs) > 1:
                                # 保留第一个，其余分配新 ID
                                for obj in objs[1:]:
                                    obj.awb_id = str(uuid.uuid4().int)[:8]
                                    did_heal = True
            if did_heal:
                self.report({"INFO"}, "✅ 重复 ID 已自动修复，请重新验证")
                # 验证重复 ID 是否修复完成
                v = self._revalidate()
            self.report({"ERROR"}, f"{v['summary']} — 见系统控制台")
            print(f"\n{'='*50}")
            print(f"⚠️  世界验证: {v['summary']}")
            print(f"{'='*50}")
            for e in v["errors"]:
                print(f"  ❌ [{e['code']}] {e['message']}")
                print(f"     {e['detail']}")
            for w in v["warnings"]:
                print(f"  ⚠️  [{w['code']}] {w['message']}")
                print(f"     {w['detail']}")
            print(f"{'='*50}\n")
        return {"FINISHED"}

    def _revalidate(self):
        """重新验证（修复后）"""
        import tempfile
        objects_data = []
        obj_index = 0
        for obj in bpy.context.scene.objects:
            if not has_annotation(obj):
                continue
            obj_index += 1
            oid = getattr(obj, "awb_id", f"obj_{obj_index:03d}")
            loc = obj.location
            objects_data.append({
                "id": oid,
                "label": getattr(obj, "awb_label", "") or obj.name,
                "type": getattr(obj, "awb_type", "misc"),
                "region": getattr(obj, "awb_region", ""),
                "position": {"x": loc.x, "y": loc.y, "z": loc.z},
            })
        world_data = {
            "objects": objects_data,
            "regions": _load_regions(),
            "relations": _load_relations(),
        }
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(world_data, tmp)
        tmp.close()
        try:
            db = WorldDB(tmp.name)
            return db.validate()
        finally:
            os.unlink(tmp.name)
        return {"FINISHED"}


class AWB_OT_AddRelation(Operator):
    """新增物体关系"""
    bl_idname = "awb.add_relation"
    bl_label = "新增关系"
    bl_description = "在两个物体之间建立关系"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        src_id = scene.awb_rel_source
        tgt_id = scene.awb_rel_target
        rel_type = scene.awb_rel_type

        if not src_id or not tgt_id:
            self.report({"ERROR"}, "请输入 source 和 target")
            return {"CANCELLED"}
        if src_id == tgt_id:
            self.report({"ERROR"}, "不能和自己建立关系")
            return {"CANCELLED"}

        relations = _load_relations()
        # 去重
        for r in relations:
            if r.get("source") == src_id and r.get("type") == rel_type and r.get("target") == tgt_id:
                self.report({"WARNING"}, f"关系已存在: {src_id} {rel_type} {tgt_id}")
                return {"CANCELLED"}

        relations.append({"source": src_id, "type": rel_type, "target": tgt_id})
        _save_relations(relations)
        self.report({"INFO"}, f"已添加: {src_id} {rel_type} {tgt_id}")
        return {"FINISHED"}


class AWB_OT_RemoveRelation(Operator):
    """删除关系"""
    bl_idname = "awb.remove_relation"
    bl_label = "删除关系"
    bl_description = "移除此关系"
    bl_options = {"REGISTER", "UNDO"}

    rel_index: bpy.props.IntProperty()  # type: ignore

    def execute(self, context):
        relations = _load_relations()
        if 0 <= self.rel_index < len(relations):
            removed = relations.pop(self.rel_index)
            _save_relations(relations)
            self.report({"INFO"}, f"已删除: {removed.get('source','')} {removed.get('type','')} {removed.get('target','')}")
        return {"FINISHED"}


class AWB_OT_QuickRelation(Operator):
    """快速建立关系 — 选中两个物体，选模板 → 一键建立"""
    bl_idname = "awb.quick_relation"
    bl_label = "快速关系"
    bl_description = "为选中的两个物体快速建立关系"
    bl_options = {"REGISTER", "UNDO"}

    rel_type: StringProperty(default="related_to")  # type: ignore

    def execute(self, context):
        selected = [o for o in context.selected_objects if has_annotation(o)]
        if len(selected) != 2:
            self.report({"ERROR"}, "请恰好选中 2 个已标注物体（先 Ctrl+点击两个物体）")
            return {"CANCELLED"}

        a, b = selected[0], selected[1]
        a_id = getattr(a, "awb_id", "")
        b_id = getattr(b, "awb_id", "")
        if not a_id or not b_id:
            self.report({"ERROR"}, "两个物体都需要先分配 ID")
            return {"CANCELLED"}

        relations = _load_relations()
        # 去重
        for r in relations:
            if r.get("source") == a_id and r.get("type") == self.rel_type and r.get("target") == b_id:
                self.report({"WARNING"}, "关系已存在")
                return {"CANCELLED"}

        relations.append({"source": a_id, "type": self.rel_type, "target": b_id})
        _save_relations(relations)

        a_label = getattr(a, "awb_label", a.name)
        b_label = getattr(b, "awb_label", b.name)
        self.report({"INFO"}, f"{a_label} {self.rel_type} {b_label}")
        return {"FINISHED"}


# =============================================================================
# Region Panel — 区域拓扑管理
# =============================================================================



# =============================================================================
# UI — 标注面板
# =============================================================================

class AWB_PT_MainPanel(Panel):
    """Current Object — 选中物体的语义属性编辑器"""
    bl_label = "📌 Current Object"
    bl_idname = "AWB_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "World Builder"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.active_object

        if not obj or obj.type != "MESH":
            return

        # ── 物体名称 ──
        box = layout.box()
        row = box.row(align=True)
        label = getattr(obj, "awb_label", "") or obj.name
        row.label(text=label, icon="DOT")
        awb_id = getattr(obj, "awb_id", "")
        if awb_id:
            row.label(text=f"ID:{awb_id[:8]}")
        else:
            op = row.operator("awb.assign_id", text="", icon="FILE_TICK")

        # ── 分类 ──
        cat = getattr(obj, "awb_type", "unclassified")
        row = box.row(align=True)
        row.prop(obj, 'awb_type', text="分类")
        if cat == "unclassified":
            inferred = auto_classify(obj.name)
            if inferred:
                op = row.operator("awb.auto_set_type", text="", icon="FILE_TICK")
            else:
                row.label(text="", icon="ERROR")
            # 未分类：下面内容不展示
            return

        # ── 区域 ──
        row = box.row(align=True)
        row.prop(obj, 'awb_region', text="区域")

        # ── 标签 + 预设 ──
        row = box.row(align=True)
        row.prop(obj, 'awb_flags', text="标签")
        presets = _load_presets()
        tag_presets = presets.get("flags", [])
        if tag_presets:
            flow = box.grid_flow(row_major=True, columns=5, even_columns=True, align=True)
            for t in tag_presets:
                op = flow.operator("awb.add_flag", text=t)
                op.tag = t

        # ── 交互 + 预设 ──
        row = box.row(align=True)
        row.prop(obj, 'awb_actions', text="交互")
        interaction_presets = presets.get("actions", [])
        if interaction_presets:
            flow = box.grid_flow(row_major=True, columns=5, even_columns=True, align=True)
            for it in interaction_presets:
                op = flow.operator("awb.add_action", text=it)
                op.interaction = it

        # ── 自定义属性（存在时展示） ──
        props_val = getattr(obj, "awb_properties", "")
        if props_val and props_val != "{}":
            row = box.row(align=True)
            row.prop(obj, 'awb_properties', text="Prop")

        # ── 操作按钮 ──
        layout.separator()
        row = layout.row(align=True)
        op = row.operator("awb.auto_set_type", text="🤖 智能推断", icon="LIGHT")
        row.prop(scene, "awb_auto_type_overwrite", text="覆写")

        row = layout.row(align=True)
        row.operator("awb.clear_annotation", text="清除标注", icon="X")

        # ── 快速关系（两物体选中时） ──
        selected = [o for o in context.selected_objects if has_annotation(o) and getattr(o, "awb_id", "")]
        if len(selected) == 2:
            layout.separator()
            box = layout.box()
            box.label(text="快速关系", icon="LINKED")
            s1 = getattr(selected[0], "awb_label", selected[0].name)
            s2 = getattr(selected[1], "awb_label", selected[1].name)
            box.label(text=f"{s1}  →  {s2}")
            col = box.column(align=True)
            for (rtype, rlabel, rdesc) in RELATION_TYPES:
                if rtype == "inside":
                    continue
                op = col.operator("awb.quick_relation", text=f"{rlabel} — {rdesc}")
                op.rel_type = rtype


class AWB_PT_ObservationPanel(Panel):
    """Observation Preview — 设置坐标半径 → 观察 → 面板显示结果"""
    bl_label = "👁 Observation"
    bl_idname = "AWB_PT_ObservationPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "World Builder"
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── 参数区 ──
        box = layout.box()
        box.label(text="Agent 参数", icon="VIEWZOOM")
        col = box.column(align=True)
        col.prop(scene, 'awb_obs_x', text="X")
        col.prop(scene, 'awb_obs_y', text="Y")
        col.prop(scene, 'awb_obs_z', text="Z")
        col.prop(scene, 'awb_obs_radius', text="观察半径")
        col.separator()
        col.label(text="FOV（可选）", icon="CONE")
        sub = col.row(align=True)
        sub.prop(scene, 'awb_obs_dir_x', text="Dir X")
        sub.prop(scene, 'awb_obs_dir_y', text="Y")
        sub.prop(scene, 'awb_obs_dir_z', text="Z")
        col.prop(scene, 'awb_obs_fov', text="视野角度")

        row = box.row(align=True)
        row.operator("awb.run_observation", text="从场景观察", icon="PLAY")
        row.operator("awb.run_observation_from_file", text="从文件", icon="FILE")

        # ── 结果区 ──
        raw = scene.awb_last_observation
        if not raw:
            layout.label(text="点击「从场景观察」开始", icon="INFO")
            return

        try:
            obs = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            layout.label(text="结果缓存异常，请重新观察", icon="ERROR")
            return

        visible = obs.get("visible_objects", [])
        pos = obs.get("observer_position", {})
        r = obs.get("radius", 0)

        # 摘要行
        layout.separator()
        direction = obs.get("direction")
        fov_angle = obs.get("fov_angle")
        if direction and fov_angle:
            d = direction
            summary = f"📍 ({pos.get('x',0):.1f}, {pos.get('y',0):.1f}, {pos.get('z',0):.1f})  r={r:.1f}  →({d[0]:.1f},{d[1]:.1f},{d[2]:.1f})  ∠{fov_angle}°"
        else:
            summary = f"📍 ({pos.get('x',0):.1f}, {pos.get('y',0):.1f}, {pos.get('z',0):.1f})  r={r:.1f}  (球形)"
        layout.label(text=summary, icon="GHOST_ENABLED")

        box = layout.box()
        if not visible:
            box.label(text="周围空无一物", icon="BLANK1")
        else:
            box.label(text=f"可见 {len(visible)} 个物体:", icon="OUTLINER_OB_MESH")
            for o in visible:
                self._draw_object_row(box, o)

    def _draw_object_row(self, layout, obj_data: dict):
        """绘制单个可见物体的行——可点击查看详情"""
        cat = obj_data.get("type", "misc")
        label = obj_data.get("label", "?")
        dist = obj_data.get("distance", 0)
        oid = obj_data.get("id", "")

        row = layout.row(align=True)
        # 分类图标映射
        icon = _category_icon(cat)
        row.label(text=f"[{cat}] {label}", icon=icon)
        row.label(text=f"{dist:.1f}m")
        if oid:
            op = row.operator("awb.show_detail", text="", icon="PROPERTIES")
            op.obj_id = oid


# =============================================================================
# Helpers
# =============================================================================

def _safe_float(val, default=0.0):
    """安全转换 Blender StringProperty → float"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def _collect_annotated_objects() -> list:
    """从 Blender 场景收集所有已标注物体的数据——唯一数据收集入口。"""
    objects_data = []
    obj_index = 0
    for obj in bpy.context.scene.objects:
        if not has_annotation(obj):
            continue
        obj_index += 1
        loc = obj.location
        tags_raw = str(getattr(obj, "awb_flags", ""))
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        interactions_raw = str(getattr(obj, "awb_actions", ""))
        interactions = [t.strip() for t in interactions_raw.split(",") if t.strip()]
        objects_data.append({
            "id": str(getattr(obj, "awb_id", f"obj_{obj_index:03d}")),
            "label": str(getattr(obj, "awb_label", "") or obj.name),
            "blender_name": str(obj.name),
            "type": str(getattr(obj, "awb_type", "misc")),
            "flags": tags,
            "actions": interactions,
            "region": str(getattr(obj, "awb_region", "")),
            "position": {"x": loc.x, "y": loc.y, "z": loc.z},
        })
    return objects_data


def _find_object_by_id(obj_id: str) -> dict:
    """从场景实时查找物体完整信息（用于弹出详情）。"""
    if not obj_id:
        return None
    obj_index = 0
    for obj in bpy.context.scene.objects:
        if not has_annotation(obj):
            continue
        obj_index += 1
        oid = getattr(obj, "awb_id", f"obj_{obj_index:03d}")
        if oid == obj_id:
            loc = obj.location
            tags_raw = getattr(obj, "awb_flags", "")
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            interactions_raw = getattr(obj, "awb_actions", "")
            interactions = [t.strip() for t in interactions_raw.split(",") if t.strip()]
            props_raw = getattr(obj, "awb_properties", "{}")
            try:
                props = json.loads(props_raw)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                props = {}
            return {
                "id": oid,
                "blender_name": obj.name,
                "label": getattr(obj, "awb_label", "") or obj.name,
                "type": getattr(obj, "awb_type", "misc"),
                "flags": tags,
                "actions": interactions,
                "region": getattr(obj, "awb_region", ""),
                "position": {"x": loc.x, "y": loc.y, "z": loc.z},
                "properties": props,
            }
    return None


def _category_icon(cat: str) -> str:
    """分类 → Blender icon 映射。"""
    icons = {
        "furniture": "MESH_CUBE",
        "container": "PACKAGE",
        "door": "MOD_DECIM",
        "item": "MESH_UVSPHERE",
        "character": "ARMATURE_DATA",
        "structure": "MESH_GRID",
        "nature": "FORCE_TURBULENCE",
        "light": "LIGHT_POINT",
        "region": "DRIVER",
    }
    return icons.get(cat, "MESH_CONE")


def _collect_regions() -> list:
    """
    从 Scene 属性 awb_regions 收集区域拓扑。
    如果 scene 上不存在该属性（旧版），返回空列表。
    自动对称 connections：A 连 B → B 连 A。
    """
    raw = getattr(bpy.context.scene, "awb_regions", "")
    if not raw or not isinstance(raw, str):
        return []
    try:
        regions = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return []

    # 自动对称
    if isinstance(regions, list):
        _symmetrize_connections(regions)
    return regions if isinstance(regions, list) else []


def _symmetrize_connections(regions: list):
    """确保 connections 无向：A 连 B → B 连 A。"""
    idx = {r["id"]: r for r in regions if "id" in r}
    for r in regions:
        for conn_id in r.get("connections", []):
            other = idx.get(conn_id)
            if other and r["id"] not in other.get("connections", []):
                other.setdefault("connections", []).append(r["id"])


# =============================================================================
# World Explorer — v0.9 世界浏览器面板
# =============================================================================

class AWB_OT_SelectWorldObject(Operator):
    """在场景中选中指定物体（通过 ID 或 Blender 名称查找）"""
    bl_idname = "awb.select_world_object"
    bl_label = "跳转到物体"
    bl_description = "在 3D 视图中选中该物体并框选视角"

    obj_id: StringProperty()       # type: ignore
    blender_name: StringProperty() # type: ignore

    def execute(self, context):
        target = None
        # 优先按 ID 找
        if self.obj_id:
            for obj in bpy.data.objects:
                if getattr(obj, "awb_id", "") == self.obj_id:
                    target = obj
                    break
        # 备选按 Blender 名称找
        if not target and self.blender_name:
            target = bpy.data.objects.get(self.blender_name)

        if not target:
            self.report({"WARNING"}, f"找不到物体: {self.obj_id or self.blender_name}")
            return {"CANCELLED"}

        # 取消现有选中 → 选中目标 → 设为 Active
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        context.view_layer.objects.active = target
        # 聚焦到选中物体
        bpy.ops.view3d.view_selected()
        return {"FINISHED"}



def _build_world_tree():
    """从场景中收集已标注物体，按区域 + 未分类构建树结构。"""
    try:
        return __build_world_tree()
    except Exception as e:
        return {
            "regions": {},
            "unlabeled": [],
            "all_unlabeled": 0,
            "stats": {
                "total_objects": 0,
                "total_regions": 0,
                "total_relations": 0,
                "unlabeled_mesh": 0,
            },
            "_error": str(e),
        }


def __build_world_tree():
    """从场景中收集已标注物体，按区域 + 未分类构建树结构。

    返回:
    {
        "regions": {区域名: [obj_dict, ...]},
        "unlabeled": [obj_dict, ...],
        "all_unlabeled": int,
        "stats": {total_objects, total_regions, total_relations, unlabeled_mesh}
    }
    """
    objects_data = _collect_annotated_objects()

    # 按 region 分组
    by_region = {}
    for obj in objects_data:
        region = obj.get("region", "") or "(未设区域)"
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(obj)

    # 未标注的 mesh
    all_unlabeled = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and not has_annotation(obj):
            all_unlabeled.append({
                "blender_name": obj.name,
                "label": obj.name,
            })

    # 统计 relations（清理幽灵引用：物体已被删除但关系还留着）
    relations = _load_relations()
    valid_ids = {getattr(o, 'awb_id', '') for o in bpy.context.scene.objects if o.type == 'MESH' and getattr(o, 'awb_id', '')}
    cleaned_relations = [r for r in relations if r.get('from', '') in valid_ids and r.get('to', '') in valid_ids]
    if len(cleaned_relations) != len(relations):
        _save_relations(cleaned_relations)
    total_relations = len(cleaned_relations)

    return {
        "regions": by_region,
        "unlabeled": all_unlabeled,
        "all_unlabeled": len(all_unlabeled),
        "stats": {
            "total_objects": len(objects_data),
            "total_regions": len(_collect_regions()),
            "total_relations": total_relations,
            "unlabeled_mesh": len(all_unlabeled),
        },
    }


class AWB_PT_WorldStatusPanel(Panel):
    """World Status — 世界状态概览卡"""
    bl_label = "🌎 World Status"
    bl_idname = "AWB_PT_WorldStatusPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "World Builder"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        # 自动去重——每次刷新检测一次
        _auto_clear_duplicate_ids(scene)
        tree = _build_world_tree()
        stats = tree["stats"]

        # ── 统计卡 ──
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text=f"Objects: {stats['total_objects']}", icon="OBJECT_DATA")
        row.label(text=f"Regions: {stats['total_regions']}", icon="OUTLINER_OB_LIGHT")
        row = col.row(align=True)
        row.label(text=f"Relations: {stats['total_relations']}", icon="LINKED")
        if stats['unlabeled_mesh']:
            row.label(text=f"Unlabeled: {stats['unlabeled_mesh']}", icon="ERROR")

        # ── 世界级操作 ──
        box = layout.box()
        row = box.row(align=True)
        row.operator("awb.validate_world", text="验证", icon="CHECKMARK")
        row.operator("awb.export_world", text="导出 world.json", icon="EXPORT")

class AWB_PT_WorldExplorerPanel(Panel):
    """World Explorer — 世界浏览器，树形展示 + 未分类 + 统计 + 点击跳转 + 批量编辑"""
    bl_label = "🌍 World Explorer"
    bl_idname = "AWB_PT_WorldExplorerPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "World Builder"
    bl_order = 3

    def draw(self, context):
        try:
            self._draw(context)
        except Exception as e:
            self.layout.label(text=f"Explorer 错误: {e}", icon="ERROR")

    def _draw(self, context):
        layout = self.layout
        scene = context.scene

        # 获取已标注物体
        try:
            objs = _collect_annotated_objects()
        except Exception:
            objs = []

        # ── 统计行 ──
        box = layout.box()
        row = box.row(align=True)
        row.label(text="total: " + str(len(objs)), icon="OBJECT_DATA")
        total_regions = len(set(o.get("region", "") for o in objs if o.get("region", "")))
        row.label(text="regions: " + str(total_regions), icon="OUTLINER_OB_LIGHT")
        row.label(text="unlabeled: " + str(len([o for o in context.scene.objects if not has_annotation(o)])), icon="ERROR")

        if not objs:
            layout.separator()
            layout.label(text="没有已标注的物体", icon="INFO")
            return

        layout.separator()

        # ── 按区域分组 ──
        by_region = {}
        for o in objs:
            r = o.get("region", "") or "(未设区域)"
            by_region.setdefault(r, []).append(o)

        cat_icon_map = {
            "furniture": "MESH_CUBE", "container": "MESH_CYLINDER",
            "doorway": "MOD_MIRROR", "item": "OUTLINER_OB_LIGHT",
            "lighting": "LIGHT_POINT", "natural": "OUTLINER_DATA_LIGHTPROBE",
            "structure": "MOD_BUILD", "character": "OUTLINER_OB_ARMATURE",
            "area": "OUTLINER_OB_LIGHTPROBE",
        }

        for region_name in sorted(by_region.keys()):
            objects = by_region[region_name]
            icon = "HOME" if region_name != "(未设区域)" else "GHOST_ENABLED"
            box = layout.box()
            row = box.row(align=True)
            row.label(text="  " + region_name + " (" + str(len(objects)) + ")", icon=icon)
            col = box.column(align=True)
            for o in objects:
                row = col.row(align=True)
                cat = o.get("type", "misc")
                cat_icon = cat_icon_map.get(cat, "DOT")
                oid = o.get("id", "")
                label = o.get("label", "?")
                tags = o.get("flags", [])
                tag_text = ", ".join(tags[:2]) if tags else ""
                text = "  " + label
                if oid:
                    text += " [" + oid[:6] + "]"
                if tag_text:
                    text += " - " + tag_text
                row.label(text=text, icon=cat_icon)
                op = row.operator("awb.select_world_object", text="", icon="RESTRICT_SELECT_OFF")
                op.blender_name = o.get("blender_name", "")



# =============================================================================
# Registration
# =============================================================================

CLASSES = [
    AWB_OT_SelectWorldObject,
    AWB_OT_ExportWorld,
    AWB_OT_AssignID,
    AWB_OT_ClearAnnotation,
    AWB_OT_CheckUnlabeled,
    AWB_OT_AutoSetType,
    AWB_OT_AddFlag,
    AWB_OT_AddAction,
    AWB_OT_RunObservation,
    AWB_OT_RunObservationFromFile,
    AWB_OT_ShowObjectDetail,
    AWB_OT_AddRegion,
    AWB_OT_RemoveRegion,
    AWB_OT_PickConnRegion,
    AWB_OT_ConnectRegions,
    AWB_OT_DisconnectRegions,
    AWB_OT_ValidateWorld,
    AWB_OT_AddRelation,
    AWB_OT_RemoveRelation,
    AWB_OT_QuickRelation,
    AWB_PT_WorldStatusPanel,
    AWB_PT_MainPanel,
    AWB_PT_WorldExplorerPanel,
    AWB_PT_ObservationPanel,
    AWB_PT_WorldManagementPanel,
]

_registry = []

def _register_scene_properties():
    """注册所有 Scene + Object 级别属性"""
    
    # === Object 级别属性（每个物体上可直接 prop 编辑）===
    if not hasattr(bpy.types.Object, "awb_type"):
        bpy.types.Object.awb_type = EnumProperty(
            name="分类",
            items=TYPE_ENUM,
            default="unclassified",
            description="物体语义分类"
        )
    if not hasattr(bpy.types.Object, "awb_flags"):
        bpy.types.Object.awb_flags = StringProperty(
            name="标签",
            default="",
            description="逗号分隔的特征标签"
        )
    if not hasattr(bpy.types.Object, "awb_actions"):
        bpy.types.Object.awb_actions = StringProperty(
            name="交互",
            default="",
            description="逗号分隔的交互行为"
        )
    if not hasattr(bpy.types.Object, "awb_region"):
        bpy.types.Object.awb_region = StringProperty(
            name="区域",
            default="",
            description="所属区域名称"
        )
    if not hasattr(bpy.types.Object, "awb_label"):
        bpy.types.Object.awb_label = StringProperty(
            name="名称",
            default="",
            description="语义名称（留空用物体名）"
        )
    if not hasattr(bpy.types.Object, "awb_id"):
        bpy.types.Object.awb_id = StringProperty(
            name="ID",
            default="",
            description="唯一标识符"
        )
    if not hasattr(bpy.types.Object, "awb_properties"):
        bpy.types.Object.awb_properties = StringProperty(
            name="属性",
            default="{}",
            description="JSON 格式自定义属性"
        )
    
    # === Scene 级别属性 ===
    # 搜索 & 筛选
    bpy.types.Scene.awb_search_text = EnumProperty(
        name="区域筛选",
        items=lambda self, ctx: _get_search_region_items(ctx),
        description="选择区域快速定位"
    )
    bpy.types.Scene.awb_filter_category = EnumProperty(
        name="分类筛选",
        items=lambda self, ctx: _get_category_filter_items(ctx),
        description="按分类筛选"
    )
    bpy.types.Scene.awb_filter_tag = EnumProperty(
        name="标签筛选",
        items=lambda self, ctx: _get_tag_filter_items(ctx),
        description="按标签筛选"
    )
    # 观察
    bpy.types.Scene.awb_obs_x = StringProperty(name="awb_obs_x", default="0")
    bpy.types.Scene.awb_obs_y = StringProperty(name="awb_obs_y", default="0")
    bpy.types.Scene.awb_obs_z = StringProperty(name="awb_obs_z", default="0")
    bpy.types.Scene.awb_obs_radius = StringProperty(name="awb_obs_radius", default="5.0")
    bpy.types.Scene.awb_obs_running = BoolProperty(name="awb_obs_running", default=False)
    bpy.types.Scene.awb_obs_dir_x = StringProperty(name="awb_obs_dir_x", default="0")
    bpy.types.Scene.awb_obs_dir_y = StringProperty(name="awb_obs_dir_y", default="0")
    bpy.types.Scene.awb_obs_dir_z = StringProperty(name="awb_obs_dir_z", default="0")
    bpy.types.Scene.awb_obs_fov = StringProperty(name="awb_obs_fov", default="0")
    bpy.types.Scene.awb_last_observation = StringProperty(name="awb_last_observation", default="")
    # 关系
    bpy.types.Scene.awb_rel_source = StringProperty(name="awb_rel_source", default="")
    bpy.types.Scene.awb_rel_target = StringProperty(name="awb_rel_target", default="")
    bpy.types.Scene.awb_rel_type = StringProperty(name="awb_rel_type", default="related_to")
    bpy.types.Scene.awb_conn_src = StringProperty(name="awb_conn_src", default="")
    bpy.types.Scene.awb_conn_dst = StringProperty(name="awb_conn_dst", default="")
    # 区域
    bpy.types.Scene.awb_new_region_name = StringProperty(name="awb_new_region_name", default="")
    bpy.types.Scene.awb_regions = StringProperty(name="awb_regions", default="")
    bpy.types.Scene.awb_relations = StringProperty(name="awb_relations", default="[]")
    bpy.types.Scene.awb_conn_idx_a = IntProperty(name="awb_conn_idx_a", default=-1)
    # 高级面板开关
    bpy.types.Scene.awb_show_advanced = BoolProperty(name="awb_show_advanced", default=False)
    # 智能推断覆写开关
    bpy.types.Scene.awb_auto_type_overwrite = BoolProperty(name="awb_auto_type_overwrite", default=False)

def _unregister_scene_properties():
    """注销所有 Scene + Object 级别属性"""
    # Object 属性
    obj_props = [
        "awb_type", "awb_flags", "awb_actions",
        "awb_region", "awb_label", "awb_id", "awb_properties",
    ]
    for prop in obj_props:
        try:
            delattr(bpy.types.Object, prop)
        except AttributeError:
            pass
    
    # Scene 属性
    scene_props = [
        "awb_obs_x", "awb_obs_y", "awb_obs_z", "awb_obs_radius",
        "awb_obs_dir_x", "awb_obs_dir_y", "awb_obs_dir_z", "awb_obs_fov",
        "awb_obs_running", "awb_last_observation",
        "awb_rel_source", "awb_rel_target", "awb_rel_type",
        "awb_conn_src", "awb_conn_dst",
        "awb_new_region_name", "awb_conn_idx_a",
        "awb_regions", "awb_relations",
        "awb_show_advanced",
    ]
    for prop in scene_props:
        try:
            delattr(bpy.types.Scene, prop)
        except AttributeError:
            pass



_awb_known_mesh_names = set()


@bpy.app.handlers.persistent
def _awb_on_depsgraph(scene, depsgraph):
    """depsgraph 更新：检测新增 mesh 物体，清空其 awb 标注属性。
    
    用物体名集合追踪已知物体。Blender Shift+D 深拷贝自定义属性，
    此 handler 发现不在已知集合里的新物体时清空其标注。"""
    global _awb_known_mesh_names
    try:
        current = {o.name for o in scene.objects if o.type == 'MESH'}
        new_names = current - _awb_known_mesh_names
        removed = _awb_known_mesh_names - current
        _awb_known_mesh_names = current  # 同步：删除物体时自动缩水
        for name in new_names:
                obj = scene.objects.get(name)
                if obj and getattr(obj, 'awb_id', ''):
                    obj.awb_id = ''
                    obj.awb_label = ''
                    obj.awb_type = 'unclassified'
                    obj.awb_flags = ''
                    obj.awb_actions = ''
                    obj.awb_region = ''
                    obj.awb_properties = '{}'
    except Exception:
        pass


def _auto_clear_duplicate_ids(scene):
    """面板刷新时兜底：检测复制物体，清空其 awb_id。"""
    import re
    try:
        for obj in scene.objects:
            if obj.type != 'MESH':
                continue
            if not getattr(obj, 'awb_id', ''):
                continue
            if re.search(r'\.\d{3}$', obj.name):
                obj.awb_id = ''
                obj.awb_label = ''
    except Exception:
        pass



def register():
    _register_scene_properties()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
        _registry.append(cls)

    # 已知物体追踪 + handler：检测复制物体
    global _awb_known_mesh_names
    try:
        _awb_known_mesh_names = {o.name for o in bpy.context.scene.objects if o.type == 'MESH'}
    except Exception:
        _awb_known_mesh_names = set()
    bpy.app.handlers.depsgraph_update_post.append(_awb_on_depsgraph)

    # 从 blend 文件旁恢复区域+关系
    _load_all_from_file()

    # 清理旧版 Enum 残留
    try:
        for scene_attr in ["awb_search_text", "awb_filter_category", "awb_filter_tag"]:
            val = getattr(bpy.context.scene, scene_attr, "")
            if val and isinstance(val, str) and len(val) <= 10:
                # 检查是否是合法的 Enum 值
                try:
                    val.encode("ascii")
                    # 纯 ASCII 小值可能是合法的
                    if not any(0x4E00 <= ord(c) <= 0x9FFF for c in val):
                        # 非中文非合法分类 → 可能是残值，重设
                        if val not in ["furniture", "container", "doorway", "item", "lighting", "natural", "structure", "character", "area", ""]:
                            setattr(bpy.context.scene, scene_attr, "")
                except UnicodeEncodeError:
                    setattr(bpy.context.scene, scene_attr, "")
    except Exception:
        pass

def unregister():
    if _awb_on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_awb_on_depsgraph)

    _unregister_scene_properties()
    for cls in reversed(_registry):
        bpy.utils.unregister_class(cls)
    _registry.clear()

if __name__ == "__main__":
    register()
