"""
Observation Builder v2.0
========================
观察层。接收 v2 物体列表 + 坐标 + 半径，返回可见物精简视图。

与 WorldDB v2 的关系：
  WorldDB.QueryAPI 告诉你 "物体是什么"（完整 schema + state）
  Observation 告诉你 "能看到什么"（精简列表，够 AI 决策）

  流程：AI 先 observe → 对感兴趣的物体再查 api.get_object(id)

v2 变化：
  - 输入物体来自 WorldDB.objects（type/attrs/region 格式）
  - state.position 替代旧的 object.position
  - 输出精简：id / label / type / distance / position / flags / contained_by
  - 不包含 attrs / template / inventory 等详情（AI 需要时自己去 query）

Usage:
    # Python API
    from observation_builder import observe
    from world_db_v2 import WorldDB

    db = WorldDB()
    db.load("world.json", "state.json")
    obs = observe(db, position=(2, 0, 1.5), radius=5)

    # CLI（v2 兼容）
    python observation_builder.py -w world_v2.json -s state.json -p 2,0,1.5 -r 5
"""

import math
import argparse
import sys
import os
from datetime import datetime, timezone


# =============================================================================
# v2 输出字段
# =============================================================================

# 精简视图字段——足够 AI 做决策
V2_OUTPUT_KEYS = [
    "id",
    "label",
    "type",
    "distance",
    "position",
    "flags",
    "contained_by",
    "region",
]


def _unpack_pos(pos):
    """兼容 tuple (x,y,z) 和 dict {'x':..., 'y':..., 'z':...}"""
    if isinstance(pos, dict):
        return float(pos.get('x', 0)), float(pos.get('y', 0)), float(pos.get('z', 0))
    return float(pos[0]), float(pos[1]), float(pos[2])


# =============================================================================
# Core — observe()
# =============================================================================

def observe(db_or_objects, position: tuple, radius: float,
            direction: tuple = None, fov_angle: float = None) -> dict:
    """
    执行一次观察。

    支持两种输入：
    1. WorldDB 实例 — 自动取 db.objects + db.states（推荐）
    2. 裸物体列表 — 兼容纯 dict 输入（每个物体必须有 id / label / type / region / position）

    Args:
        db_or_objects: WorldDB 实例，或物体 dict 列表
        position:      观察者坐标 (x, y, z)
        radius:        球形观察半径（米）
        direction:     观察者面朝方向 (dx, dy, dz)，可选。传了才参与 FOV 筛选
        fov_angle:     视野角度（度数），如 120.0，可选。与 direction 配合使用

    Returns:
        observation dict:
        {
            observer_position: {x, y, z},
            radius: float,
            visible_objects: [{id, label, type, distance, position, flags, contained_by, region}, ...],
            direction: {x, y, z} | None,   # 仅 FOV 模式
            fov_angle: float | None,        # 仅 FOV 模式
            timestamp: str
        }

    规则（来自 AI_WORLD_API.md）：
    - contained_by 不为 null 的物体不出现在结果中（它在容器里，不可见）
    - 按距离升序排列
    - direction=None → 球形全向视野（兼容旧行为）
    - direction + fov_angle → 物体与观察方向夹角 ≤ fov_angle/2 才可见
    """
    px, py, pz = _unpack_pos(position)
    radius = float(radius)

    # 预处理方向向量（只算一次）
    dx_dir, dy_dir, dz_dir = 0.0, 0.0, 0.0
    use_fov = direction is not None and fov_angle is not None
    if use_fov:
        dl = math.sqrt(direction[0]**2 + direction[1]**2 + direction[2]**2)
        if dl > 0:
            dx_dir = direction[0] / dl
            dy_dir = direction[1] / dl
            dz_dir = direction[2] / dl
            half_fov_cos = math.cos(math.radians(fov_angle / 2.0))
        else:
            use_fov = False  # 零方向向量退化为全向

    # ── 统一取 objects + states ──────────────
    objects = _resolve_objects(db_or_objects)

    visible = []
    for obj in objects:
        # 跳过硬塞在容器里的物体——它们在容器内部，视野看不到
        if obj.get("contained_by") is not None:
            continue

        # 取出位置
        pos = obj.get("position")
        if pos is None:
            continue

        ox, oy, oz = _unpack_pos(pos)
        dist = _distance(px, py, pz, ox, oy, oz)

        if dist <= radius:
            # ── FOV 视野锥过滤 ──
            if use_fov:
                dx_obj = ox - px
                dy_obj = oy - py
                dz_obj = oz - pz
                od = math.sqrt(dx_obj**2 + dy_obj**2 + dz_obj**2)
                if od > 0:
                    dx_obj /= od
                    dy_obj /= od
                    dz_obj /= od
                    dot = dx_obj * dx_dir + dy_obj * dy_dir + dz_obj * dz_dir
                    dot = max(-1.0, min(1.0, dot))
                    # 用点积比较代替角度（避免 acos 边界不稳定）
                    if dot < half_fov_cos - 5e-15:
                        continue  # 不在视野锥内

            visible.append(_slim_v2(obj, dist))

    visible.sort(key=lambda o: o["distance"])

    result = {
        "observer_position": {"x": round(px, 4), "y": round(py, 4), "z": round(pz, 4)},
        "radius": round(radius, 4),
        "visible_objects": visible,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if use_fov:
        result["direction"] = {"x": round(dx_dir, 4), "y": round(dy_dir, 4), "z": round(dz_dir, 4)}
        result["fov_angle"] = fov_angle
    return result


def _resolve_objects(db_or_objects) -> list:
    """解析输入，返回标准化的物体列表（每个都有 position/contained_by）。

    支持两种输入：
    1. WorldDB 实例 — 通过 duck-typing 检测（有 .objects 和 .states 属性）
    2. 裸 dict 列表 — 直接透传
    """
    # Duck-typing：有 objects + states 属性就是 WorldDB 实例
    if hasattr(db_or_objects, 'objects') and hasattr(db_or_objects, 'states'):
        result = []
        for oid, obj in db_or_objects.objects.items():
            state = db_or_objects.states.get(oid)
            item = {
                "id": obj.id,
                "label": obj.label,
                "type": obj.type,
                "region": obj.region,
                "position": list(state.position) if state and state.position else None,
                "contained_by": state.contained_by if state else None,
                "flags": dict(state.flags) if state and state.flags else {},
            }
            result.append(item)
        return result

    # 裸 dict 列表
    return list(db_or_objects)


def _slim_v2(obj: dict, distance: float) -> dict:
    """从完整物体裁剪到 v2 精简视图。"""
    return {
        "id": obj.get("id", ""),
        "label": obj.get("label", ""),
        "type": obj.get("type", "unknown"),
        "distance": round(distance, 4),
        "position": obj.get("position"),
        "flags": obj.get("flags", {}),
        "contained_by": obj.get("contained_by"),
        "region": obj.get("region"),
    }


def _distance(x1, y1, z1, x2, y2, z2) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


# =============================================================================
# 文本格式化
# =============================================================================

def format_observation_text(observation: dict) -> str:
    """将 observation 格式化为人类可读的多行文本。"""
    pos = observation["observer_position"]
    r = observation["radius"]
    visible = observation["visible_objects"]

    # 头部
    dir_str = ""
    if observation.get("direction"):
        d = observation["direction"]
        dir_str = f" → ({d['x']:.1f},{d['y']:.1f},{d['z']:.1f})"
    fov_str = f"  fov={observation['fov_angle']}°" if observation.get("fov_angle") else ""

    lines = [
        f"Observation @ ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}){dir_str}  r={r}{fov_str}",
        f"可见: {len(visible)} 个物体",
        "-" * 50,
    ]
    if visible:
        for o in visible:
            cb = f" ↳ {o['contained_by']}" if o.get("contained_by") else ""
            flag_bits = []
            if o.get("flags"):
                for k, v in o["flags"].items():
                    if v:
                        flag_bits.append(k)
            flags_str = f" [{', '.join(flag_bits)}]" if flag_bits else ""
            lines.append(
                f"  [{o['type']:12s}] {o['label']:12s}  {o['distance']:6.2f}m{flags_str}{cb}"
            )
    else:
        lines.append("  (周围空无一物)")
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Observation Builder v2 — 球形视野观察",
    )
    parser.add_argument("-w", "--world", required=True, help="world.json 路径")
    parser.add_argument("-s", "--state", help="state.json 路径（可选）")
    parser.add_argument("-p", "--position", required=True,
                        help="观察者坐标: x,y,z")
    parser.add_argument("-r", "--radius", type=float, default=5.0,
                        help="观察半径（米），默认 5")
    parser.add_argument("-d", "--direction", help="观察方向: x,y,z（配合 --fov 使用）")
    parser.add_argument("--fov", type=float, help="视野角度（度数），如 120")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("--text", action="store_true",
                        help="以可读文本格式输出")

    args = parser.parse_args()

    try:
        from world_db_v2 import WorldDB
    except ImportError:
        print("错误: world_db_v2 包未安装", file=sys.stderr)
        print("提示: pip install world-db-v2 或将 world_db_v2/ 放入搜索路径", file=sys.stderr)
        sys.exit(1)
    try:
        db = WorldDB()
        db.load(args.world, args.state)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        parts = [float(x.strip()) for x in args.position.split(",")]
        if len(parts) != 3:
            raise ValueError
    except ValueError:
        print("错误: --position 格式应为 x,y,z", file=sys.stderr)
        sys.exit(1)

    dir_tuple = None
    if args.direction:
        dir_tuple = tuple(float(x) for x in args.direction.split(","))
    obs = observe(db, position=tuple(parts), radius=args.radius,
                  direction=dir_tuple, fov_angle=args.fov)

    if args.text:
        output = format_observation_text(obs)
    else:
        import json
        output = json.dumps(obs, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"观察结果已写入: {args.output}  ({len(obs['visible_objects'])} 个可见物体)")
    else:
        print(output)


if __name__ == "__main__":
    main()
