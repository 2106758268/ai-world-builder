#!/usr/bin/env python3
"""
World Database — v0.2
======================
世界库。加载 world.json，提供按 ID / 分类 / 区域 查询完整对象信息。

Observation 告诉 AI "有什么"，WorldDB 告诉 AI "它是什么、能干嘛"。

Usage:
    from world_db import WorldDB
    db = WorldDB("world.json")
    obj = db.lookup("obj_003")                    # 单个查询 → 完整 Object Schema
    objs = db.lookup_many(["obj_001","obj_003"])  # 批量查询
    cat_objs = db.by_category("container")        # 按分类筛选
    region_objs = db.by_region("客厅")             # 按区域筛选
    s = db.stats()                                 # 世界库统计

CLI:
    python world_db.py world.json --lookup obj_001
    python world_db.py world.json --stats
"""

import json
import os
import argparse
import sys
from typing import Optional


class WorldDB:
    """
    世界数据库。加载 world.json，提供对象 / 区域 / 关系查询 + 验证。

    职责边界：
      ✅ 存储完整 Object Schema + Region Schema + Relations
      ✅ 按 ID / 分类 / 区域 / 关系类型查询
      ✅ 区域连通 + 物体关系自动反向推导
      ✅ 统计信息
      ✅ 世界完整性验证
      ❌ 不做空间计算（那是 Observation 的事）
      ❌ 不做视野筛选（那是 Observation 的事）
    """

    # 关系类型 → 反向类型
    _REVERSE_RELATION = {
        "contains": "inside",
        "inside": "contains",
        "connects_to": "connects_to",
        "unlocks": "unlocked_by",
        "activates": "activated_by",
        "owns": "owned_by",
        "knows": "known_by",
        "uses": "used_by",
        "related_to": "related_to",
    }

    # 合法枚举
    VALID_CATEGORIES = {
        "furniture", "container", "door", "item",
        "character", "structure", "nature", "light", "region", "misc",
    }
    VALID_RELATION_TYPES = set(_REVERSE_RELATION.keys())

    def __init__(self, path: str):
        self.path = path
        self.metadata: dict = {}
        self.objects: list = []
        self.regions: list = []            # [{id, name, connections}]
        self.relations: list = []          # [{source, type, target}]
        self._index: dict = {}             # id → object
        self._region_index: dict = {}      # region_id → region dict
        self._region_by_name: dict = {}    # region_name → region dict
        self._by_category: dict = {}       # category → [object]
        self._by_region: dict = {}         # region → [object]
        self._rel_from: dict = {}          # source_id → [relation]
        self._rel_to: dict = {}            # target_id → [derived reverse relation]
        self._load(path)

    # ── 查询 API ──

    def lookup(self, obj_id: str) -> Optional[dict]:
        """按 ID 查询单个物体的完整信息。返回 None 如果不存在。"""
        return self._index.get(obj_id)

    def lookup_many(self, obj_ids: list) -> list:
        """批量按 ID 查询，缺失的自动跳过。"""
        return [self._index[oid] for oid in obj_ids if oid in self._index]

    def by_category(self, category: str) -> list:
        """返回指定分类的所有物体（完整 schema）。"""
        return self._by_category.get(category, [])

    def by_region(self, region: str) -> list:
        """返回指定区域的所有物体（完整 schema）。region 可以是 name 或 id。"""
        reg = self.get_region(region)
        if reg:
            return self._by_region.get(reg["name"], [])
        return self._by_region.get(region, [])

    # ── Region API ──

    def get_region(self, region_id_or_name: str) -> Optional[dict]:
        """按 id 或 name 查询区域。"""
        return self._region_index.get(region_id_or_name) or \
               self._region_by_name.get(region_id_or_name)

    def connected_regions(self, region_id_or_name: str) -> list:
        """返回与该区域相连的所有区域 dict 列表。"""
        reg = self.get_region(region_id_or_name)
        if not reg:
            return []
        result = []
        for rid in reg.get("connections", []):
            r = self._region_index.get(rid)
            if r:
                result.append(r)
        return result

    # ── Relation API ──

    def relations_of(self, obj_id: str) -> list:
        """
        返回该物体参与的所有关系。
        包含正向（我→别人）+ 反向推导（别人→我）。
        每条关系格式: {source, type, target, derived: bool}
        """
        result = []
        # 正向：我是 source
        for rel in self._rel_from.get(obj_id, []):
            result.append({**rel, "derived": False})
        # 反向推导：我是 target
        for rel in self._rel_to.get(obj_id, []):
            result.append({**rel, "derived": True})
        return result

    def find_relations(self, rel_type: str = None, source: str = None, target: str = None) -> list:
        """
        按条件查询关系。支持 type / source / target 组合过滤。
        """
        results = []
        for rel in self.relations:
            if rel_type and rel.get("type") != rel_type:
                continue
            if source and rel.get("source") != source:
                continue
            if target and rel.get("target") != target:
                continue
            results.append(rel)
        return results

    def related_objects(self, obj_id: str) -> list:
        """
        返回与 obj_id 有关联的所有物体 ID 列表。
        """
        ids = set()
        for rel in self.relations:
            if rel["source"] == obj_id:
                ids.add(rel["target"])
            elif rel["target"] == obj_id:
                ids.add(rel["source"])
        return list(ids)

    # ── Stats ──

    def stats(self) -> dict:
        """返回世界库统计信息。"""
        region_names = [r["name"] for r in self.regions]
        return {
            "total_objects": len(self.objects),
            "total_regions": len(self.regions),
            "total_relations": len(self.relations),
            "regions": region_names,
            "categories": {k: len(v) for k, v in self._by_category.items()},
        }

    # ── Validation ──

    def validate(self) -> dict:
        """
        验证世界完整性，返回 {errors: [{code, message, detail}], warnings: [...]}。

        检查项：
          1. Object IDs — 缺失 / 重复 / 格式
          2. Region IDs — 缺失 / 重复
          3. Relation References — source/target 指向不存在
          4. Category Enum — 不在合法枚举中
          5. Region References — 物体 region 指向不存在的区域
          6. Orphan Objects — 已标注但无 region
        """
        errors = []
        warnings = []
        e = errors.append
        w = warnings.append

        # ── 1. Object IDs ──
        seen_ids = {}
        obj_with_region = 0
        for i, obj in enumerate(self.objects):
            oid = obj.get("id", "")
            if not oid:
                label = obj.get("label", obj.get("blender_name", f"#{i}"))
                e({"code": "MISSING_OBJECT_ID",
                    "message": f"物体缺少 ID",
                    "detail": f"label=\"{label}\" (index {i})"})
                continue
            if oid in seen_ids:
                e({"code": "DUPLICATE_OBJECT_ID",
                    "message": f"重复的 Object ID",
                    "detail": f"id=\"{oid}\" 同时属于「{obj.get('label','')}」和「{seen_ids[oid]}」"})
            else:
                seen_ids[oid] = obj.get("label", "")
            if obj.get("region", ""):
                obj_with_region += 1

        # ── 2. Region IDs ──
        seen_reg_ids = {}
        for reg in self.regions:
            rid = reg.get("id", "")
            if not rid:
                e({"code": "MISSING_REGION_ID",
                    "message": "区域缺少 ID",
                    "detail": f"name=\"{reg.get('name','')}\""})
                continue
            if rid in seen_reg_ids:
                e({"code": "DUPLICATE_REGION_ID",
                    "message": f"重复的 Region ID",
                    "detail": f"id=\"{rid}\" →「{seen_reg_ids[rid]}」和「{reg.get('name','')}」"})
            else:
                seen_reg_ids[rid] = reg.get("name", "")

        # ── 3. Relation References ──
        all_obj_ids = set(self._index.keys())
        for rel in self.relations:
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            rtype = rel.get("type", "?")
            if src and src not in all_obj_ids:
                e({"code": "ORPHAN_RELATION_SOURCE",
                    "message": f"关系 source 指向不存在的物体",
                    "detail": f"{rtype}: {src} → {tgt}"})
            if tgt and tgt not in all_obj_ids:
                e({"code": "ORPHAN_RELATION_TARGET",
                    "message": f"关系 target 指向不存在的物体",
                    "detail": f"{rtype}: {src} → {tgt}"})

        # ── 4. Category Enum ──
        for obj in self.objects:
            cat = obj.get("category", "")
            if cat and cat not in self.VALID_CATEGORIES:
                w({"code": "UNKNOWN_CATEGORY",
                    "message": f"未知分类",
                    "detail": f"「{obj.get('label','')}」的 category=\"{cat}\"，不在合法枚举中"})

        # ── 5. Region References ──
        known_region_names = set(self._region_by_name.keys())
        known_region_ids = set(self._region_index.keys())
        for obj in self.objects:
            reg = obj.get("region", "")
            if reg and reg not in known_region_names and reg not in known_region_ids:
                w({"code": "UNKNOWN_REGION",
                    "message": f"物体引用了不存在的区域",
                    "detail": f"「{obj.get('label','')}」的 region=\"{reg}\" 不在 regions[] 中"})

        # ── 6. Orphan Objects ──
        total_annotated = len(self.objects)
        if total_annotated > 0 and obj_with_region == 0:
            w({"code": "NO_REGIONS_ASSIGNED",
                "message": f"{total_annotated} 个已标注物体均未设置 region",
                "detail": "建议为物体分配区域"})

        return {"errors": errors, "warnings": warnings,
                "passed": len(errors) == 0,
                "summary": f"{len(errors)} 错误, {len(warnings)} 警告"}

    # ── 内部 ──

    def _load(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"world.json 未找到: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.metadata = data.get("metadata", {})
        self.objects = data.get("objects", [])
        self.regions = data.get("regions", [])
        self.relations = data.get("relations", [])
        self._build_index()

    def _build_index(self):
        """构建 id / category / region / relations 索引。"""
        self._index.clear()
        self._by_category.clear()
        self._by_region.clear()
        self._region_index.clear()
        self._region_by_name.clear()
        self._rel_from.clear()
        self._rel_to.clear()

        for obj in self.objects:
            oid = obj.get("id", "")
            if oid:
                self._index[oid] = obj
            cat = obj.get("category", "misc")
            self._by_category.setdefault(cat, []).append(obj)
            reg = obj.get("region", "") or "(未设区域)"
            self._by_region.setdefault(reg, []).append(obj)

        for reg in self.regions:
            rid = reg.get("id", "")
            rname = reg.get("name", "")
            if rid:
                self._region_index[rid] = reg
            if rname:
                self._region_by_name[rname] = reg

        # 关系索引 — 正向 + 自动反向推导
        for rel in self.relations:
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            rtype = rel.get("type", "")
            if src:
                self._rel_from.setdefault(src, []).append(rel)
            # 反向推导
            reverse_type = self._REVERSE_RELATION.get(rtype, "related_to")
            derived = {"source": tgt, "type": reverse_type, "target": src}
            if tgt:
                self._rel_to.setdefault(tgt, []).append(derived)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="World Database 查询工具")
    parser.add_argument("world", help="world.json 路径")
    parser.add_argument("--lookup", help="按 ID 查询详情")
    parser.add_argument("--stats", action="store_true", help="显示世界库统计")
    parser.add_argument("--category", help="按分类列物体")
    parser.add_argument("--region", help="按区域列物体")
    parser.add_argument("--connections", help="显示某区域的连通关系")
    parser.add_argument("--relations", help="显示某物体的所有关系")
    parser.add_argument("--rel-type", help="按关系类型筛选")
    parser.add_argument("--validate", action="store_true", help="验证世界完整性")

    args = parser.parse_args()
    try:
        db = WorldDB(args.world)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    if args.stats:
        s = db.stats()
        print(f"世界库: {s['total_objects']} 个物体, {s['total_regions']} 个区域")
        print(f"  区域: {s['regions']}")
        print(f"  分类: {s['categories']}")
        return

    if args.validate:
        v = db.validate()
        if v["passed"]:
            print("✅ 验证通过 — 无错误")
        else:
            print(f"❌ 验证失败: {v['summary']}")
        for e in v["errors"]:
            print(f"  [ERROR] {e['code']}: {e['message']}")
            print(f"           {e['detail']}")
        for w in v["warnings"]:
            print(f"  [WARN]  {w['code']}: {w['message']}")
            print(f"           {w['detail']}")
        return

    if args.lookup:
        obj = db.lookup(args.lookup)
        if obj:
            print(json.dumps(obj, ensure_ascii=False, indent=2))
        else:
            print(f"未找到: {args.lookup}")
        return

    if args.category:
        objs = db.by_category(args.category)
        print(f"分类 [{args.category}]: {len(objs)} 个")
        for o in objs:
            print(f"  {o['label']:12s} (region: {o.get('region','')})")
        return

    if args.region:
        objs = db.by_region(args.region)
        print(f"区域 [{args.region}]: {len(objs)} 个")
        for o in objs:
            print(f"  {o['label']:12s} ({o.get('category','')})")
        return

    if args.connections:
        reg = db.get_region(args.connections)
        if not reg:
            print(f"未找到区域: {args.connections}")
            return
        conn = db.connected_regions(args.connections)
        print(f"{reg['name']} ({reg['id']})")
        if conn:
            print(f"  连通:")
            for c in conn:
                print(f"    → {c['name']} ({c['id']})")
        else:
            print(f"  (与其他区域无连接)")
        return

    if args.relations:
        rels = db.relations_of(args.relations)
        obj = db.lookup(args.relations)
        name = obj["label"] if obj else args.relations
        if not rels:
            print(f"{name} 没有关系")
            return
        print(f"{name} 的关系:")
        for r in rels:
            other_id = r["target"]
            other = db.lookup(other_id)
            other_name = other["label"] if other else other_id
            derived = "(推导)" if r.get("derived") else ""
            print(f"  {r['type']:14s} → {other_name:12s} {derived}")
        return

    if args.rel_type:
        rels = db.find_relations(rel_type=args.rel_type)
        print(f"关系类型 [{args.rel_type}]: {len(rels)} 条")
        for r in rels:
            src = db.lookup(r["source"])
            tgt = db.lookup(r["target"])
            sn = src["label"] if src else r["source"]
            tn = tgt["label"] if tgt else r["target"]
            print(f"  {sn} → {tn}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
