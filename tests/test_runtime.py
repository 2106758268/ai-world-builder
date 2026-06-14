"""
test_runtime.py — WorldDB v2 Runtime Tests

测试范围：
- Load / Save
- QueryAPI 全部只读方法
- Write API: set_state / transfer
- Validate
- 边界条件

运行：
    cd ai-world-builder && python3 test_runtime.py
"""

import json
import sys
import os

# 确保能 import world_db_v2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from world_db_v2 import WorldDB, QueryAPI

PASS = 0
FAIL = 0


def check(condition, label):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}")


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ============================================================================
# 1. Load
# ============================================================================
section("1. Load")

db = WorldDB()
db.load("test_world_v2.json")
api = QueryAPI(db)

check(len(db.objects) == 6, "6 objects loaded")
check(len(db.regions) == 3, "3 regions loaded")
check(len(db.relations) == 3, "3 relations loaded")
check(len(db.states) == 6, "6 states auto-generated")
check(len(db.templates) == 6, "6 templates loaded")
check("chair_01" in db.objects, "chair_01 exists")
check("key_01" in db.objects, "key_01 exists")

# ============================================================================
# 2. QueryAPI — get_object
# ============================================================================
section("2. get_object()")

door = api.get_object("door_01")
check(door is not None, "door_01 found")
check(door["id"] == "door_01", "door_01 id correct")
check(door["label"] == "大门", "door_01 label correct")
check(door["type"] == "door", "door_01 type correct")
check(door["region"] == "entrance", "door_01 region correct")
check(door["attrs"]["material"] == "wood", "door_01 material=wood")
check(door["template"]["interactions"] == ["open", "close"], "door_01 template interactions")
check(door["state"] is not None, "door_01 has state")
check(door["state"]["flags"]["open"] == False, "door_01 open=false")
check(door["state"]["flags"]["locked"] == False, "door_01 locked=false")

chest = api.get_object("chest_01")
check(chest["type"] == "container", "chest_01 type=container")
check(chest["attrs"]["material"] == "wood", "chest_01 material=wood")
check(chest["attrs"]["kind"] == "chest", "chest_01 kind=chest")
check(chest["attrs"]["size"] == "large", "chest_01 size=large")

check(api.get_object("nonexistent") is None, "nonexistent → None")

# ============================================================================
# 3. QueryAPI — get_state
# ============================================================================
section("3. get_state()")

state = api.get_state("door_01")
check(state is not None, "door_01 state exists")
check(state.flags == {"open": False, "locked": False}, "door_01 flags correct")
check(state.position == [0, 0, 0], "door_01 default position=[0,0,0]")
check(state.contained_by is None, "door_01 contained_by=None")
check(state.inventory == [], "door_01 inventory=[]")
check(state.damaged == 0, "door_01 damaged=0")

check(api.get_state("nonexistent") is None, "nonexistent state → None")

# ============================================================================
# 4. objects_in_region
# ============================================================================
section("4. objects_in_region()")

lr = api.objects_in_region("living_room")
lr_ids = [o["id"] for o in lr]
check(len(lr) == 3, "living_room has 3 objects")
check("chair_01" in lr_ids, "chair_01 in living_room")
check("table_01" in lr_ids, "table_01 in living_room")
check("lamp_01" in lr_ids, "lamp_01 in living_room")

bed = api.objects_in_region("bedroom")
check(len(bed) == 1, "bedroom has 1 object")
check(bed[0]["id"] == "chest_01", "bedroom has chest_01")

ent = api.objects_in_region("entrance")
check(len(ent) == 1, "entrance has 1 object")
check(ent[0]["id"] == "door_01", "entrance has door_01")

check(api.objects_in_region("nonexistent") == [], "nonexistent region → []")

# ============================================================================
# 5. connected_regions
# ============================================================================
section("5. connected_regions()")

lr_conn = api.connected_regions("living_room")
check(len(lr_conn) == 2, "living_room connects to 2 regions")
lr_conn_names = [c["name"] for c in lr_conn]
check("entrance" in lr_conn_names, "living_room ↔ entrance")
check("bedroom" in lr_conn_names, "living_room ↔ bedroom")

# entrance via door_01
entrance_conn = next(c for c in lr_conn if c["name"] == "entrance")
check(entrance_conn["via"] == "door_01", "living_room↔entrance via door_01")
# bedroom has no door connecting it
bedroom_conn = next(c for c in lr_conn if c["name"] == "bedroom")
check(bedroom_conn["via"] is None, "living_room↔bedroom via None (no door)")

ent_conn = api.connected_regions("entrance")
check(len(ent_conn) == 1, "entrance connects to 1 region")
check(ent_conn[0]["name"] == "living_room", "entrance ↔ living_room")

check(api.connected_regions("nonexistent") == [], "nonexistent region → []")

# ============================================================================
# 6. related_objects
# ============================================================================
section("6. related_objects()")

# door_01 被 key_01 unlock
door_rels = api.related_objects("door_01")
check(len(door_rels) >= 1, "door_01 has relations")
unlock_rels = [(r, o) for r, o in door_rels if r.type == "unlocks"]
check(len(unlock_rels) == 1, "door_01 has 1 unlocks relation")
check(unlock_rels[0][0].source == "key_01", "unlock source=key_01")
check(unlock_rels[0][0].target == "door_01", "unlock target=door_01")
check(unlock_rels[0][1]["label"] == "铁钥匙", "unlock partner=铁钥匙")

# 反向查：key_01 也能查到它 unlock door_01
key_rels = api.related_objects("key_01")
check(len(key_rels) >= 1, "key_01 has relations (reverse)")
key_unlock = [(r, o) for r, o in key_rels if r.type == "unlocks"]
check(len(key_unlock) == 1, "key_01 -> unlocks -> door_01 (reverse)")

# 按 type 过滤
key_unlock_only = api.related_objects("key_01", "unlocks")
check(len(key_unlock_only) == 1, "related_objects filter unlocks")

key_owns = api.related_objects("key_01", "owns")
check(len(key_owns) == 0, "related_objects filter owns → empty")

# 没有 relation 的物体
chair_rels = api.related_objects("chair_01")
check(len(chair_rels) == 0, "chair_01 has no relations")

# ============================================================================
# 7. contained_by / inventory_of / has_flag / template_of
# ============================================================================
section("7. Container & flag queries")

check(api.contained_by("key_01") is None, "key_01 not contained (default)")
check(api.contained_by("chest_01") is None, "chest_01 not contained")
check(api.contained_by("nonexistent") is None, "nonexistent contained_by → None")

check(api.inventory_of("chest_01") == [], "chest_01 inventory empty")
check(api.inventory_of("key_01") == [], "key_01 inventory empty (not a container)")
check(api.inventory_of("nonexistent") == [], "nonexistent inventory → []")

check(api.has_flag("door_01", "open") == False, "has_flag open=false")
check(api.has_flag("door_01", "locked") == False, "has_flag locked=false")
check(api.has_flag("nonexistent", "open") == False, "has_flag nonexistent → False")

tmpl = api.template_of("chair_01")
check(tmpl["interactions"] == ["sit"], "chair template: sit")
check("transform" in tmpl["slots"], "chair template: transform slot")

check(api.template_of("nonexistent") is None, "template_of nonexistent → None")

# ============================================================================
# 8. Write — set_state
# ============================================================================
section("8. set_state()")

# 8a. 开门
check(db.set_state("door_01", {"flags": {"open": True, "locked": False}}), "set_state door open+unlock")
check(api.has_flag("door_01", "open") == True, "door_01 open=true")
check(api.has_flag("door_01", "locked") == False, "door_01 locked=false")

# 8b. 关门（flag 合并，不覆盖未传的）
check(db.set_state("door_01", {"flags": {"open": False}}), "set_state door close")
check(api.has_flag("door_01", "open") == False, "door_01 open=false")
check(api.has_flag("door_01", "locked") == False, "door_01 locked still false (not overwritten)")

# 8c. 推椅子
check(db.set_state("chair_01", {"position": [4, 0, 3]}), "set_state chair position")
chair_st = api.get_state("chair_01")
check(chair_st.position == [4, 0, 3], "chair_01 position=[4,0,3]")
check(chair_st.contained_by is None, "chair_01 contained_by=None (position set)")

# 8d. 把钥匙放进箱子
check(db.set_state("chest_01", {"inventory": ["key_01"]}), "set_state chest inventory=[key_01]")
check(db.set_state("key_01", {"contained_by": "chest_01"}), "set_state key contained_by=chest_01")
key_st = api.get_state("key_01")
check(key_st.contained_by == "chest_01", "key_01 contained_by=chest_01")
check(key_st.position is None, "key_01 position=null (contained)")
check(api.inventory_of("chest_01") == ["key_01"], "chest_01 inventory=[key_01]")

# 8e. damaged
check(db.set_state("chair_01", {"damaged": 50}), "set_state chair damaged=50")
check(api.get_state("chair_01").damaged == 50, "chair_01 damaged=50")
check(db.set_state("chair_01", {"damaged": 150}), "set_state chair damaged=150 (clamped)")
check(api.get_state("chair_01").damaged == 100, "chair_01 damaged=100 (clamped to 100)")
check(db.set_state("chair_01", {"damaged": -10}), "set_state chair damaged=-10 (clamped)")
check(api.get_state("chair_01").damaged == 0, "chair_01 damaged=0 (clamped to 0)")

# 8f. 不存在的 id
check(not db.set_state("nonexistent", {"position": [1, 2, 3]}), "set_state nonexistent → False")

# 8g. 从箱子里拿出来
check(db.set_state("key_01", {"position": [5, 0, 5]}), "set_state key position (takes out)")
key_st2 = api.get_state("key_01")
check(key_st2.position == [5, 0, 5], "key_01 position=[5,0,5]")
check(key_st2.contained_by is None, "key_01 contained_by=None (position set clears it)")

# ============================================================================
# 9. Write — transfer
# ============================================================================
section("9. transfer()")

# 先重置 chest_01 inventory
db.set_state("chest_01", {"inventory": []})
db.set_state("key_01", {"contained_by": None, "position": [1, 0, 1]})

# 9a. transfer key_01 into chest_01
check(db.transfer("living_room", "chest_01", "key_01") is False,
      "transfer from non-container → False (living_room not in state—test intent)")

# Actually transfer from a valid "agent" concept — use lamp as a mock for testing
check(db.set_state("lamp_01", {"inventory": ["key_01"], "flags": {"on": False}}), "setup: lamp holds key")
check(db.set_state("key_01", {"contained_by": "lamp_01", "position": None}), "setup: key in lamp")
check(api.inventory_of("lamp_01") == ["key_01"], "lamp_01 inventory=[key_01]")

# 9b. transfer from lamp to chest
check(db.transfer("lamp_01", "chest_01", "key_01"), "transfer key from lamp to chest")
check(api.inventory_of("lamp_01") == [], "lamp_01 inventory empty")
check(api.inventory_of("chest_01") == ["key_01"], "chest_01 inventory=[key_01]")
check(api.contained_by("key_01") == "chest_01", "key_01 contained_by=chest_01")
key_st3 = api.get_state("key_01")
check(key_st3.position is None, "key_01 position=null (contained)")

# 9c. transfer nonexistent
check(not db.transfer("nonexistent", "chest_01", "key_01"), "transfer nonexistent → False")

# 9d. transfer back to lamp
check(db.transfer("chest_01", "lamp_01", "key_01"), "transfer key back to lamp")
check(api.inventory_of("chest_01") == [], "chest_01 inventory empty again")
check(api.inventory_of("lamp_01") == ["key_01"], "lamp_01 inventory=[key_01]")

# ============================================================================
# 10. Save / Reload round-trip
# ============================================================================
section("10. Save / Reload")

# Save state
test_state_path = "/tmp/test_state_output.json"
db.save(state_path=test_state_path)
check(os.path.exists(test_state_path), "state saved to file")

# Load into new DB
db2 = WorldDB()
db2.load("test_world_v2.json", test_state_path)
api2 = QueryAPI(db2)

check(api2.has_flag("door_01", "open") == False, "reloaded: door closed")
check(api2.has_flag("door_01", "locked") == False, "reloaded: door unlocked")
check(api2.get_state("chair_01").damaged == 0, "reloaded: chair not damaged")
check(api2.inventory_of("lamp_01") == ["key_01"], "reloaded: key in lamp")
check(api2.contained_by("key_01") == "lamp_01", "reloaded: key contained_by=lamp")
check(api2.get_state("chair_01").position == [4, 0, 3], "reloaded: chair at [4,0,3]")

# Cleanup
os.remove(test_state_path)

# ============================================================================
# 11. Validate
# ============================================================================
section("11. validate()")

v = db.validate()
check(v["errors"] == [], "validate: 0 errors")
check(v["warnings"] == [], "validate: 0 warnings")
check(v["passed"] == 6, "validate: 6 passed")
check("6 objects" in v["summary"], "validate: summary correct")

# ============================================================================
# 12. Migration (v0.12 → v2)
# ============================================================================
section("12. Migration")

with open("test_world.json", "r", encoding="utf-8") as f:
    old_w = json.load(f)

from world_db_v2.migration import convert_v1_to_v2
w2, s2, warnings = convert_v1_to_v2(old_w)

check(len(w2["objects"]) == 8, "migrated: 8 objects")
check(len(w2["regions"]) == 4, "migrated: 4 regions")
check(len(w2["relations"]) == 1, "migrated: 1 static relation (connects)")
check(len(s2["states"]) == 8, "migrated: 8 states")
check(len(warnings) == 0, "migrated: 0 warnings")

# 检查 category→type 推断
chair = next(o for o in w2["objects"] if o["id"] == "002")
check(chair["type"] == "chair", "migrated: 002→chair (fabric+沙发)")
check(chair["attrs"]["material"] == "fabric", "migrated: 002 material=fabric")

lamp = next(o for o in w2["objects"] if o["id"] == "004")
check(lamp["type"] == "lamp", "migrated: 004→lamp")

bookcase = next(o for o in w2["objects"] if o["id"] == "005")
check(bookcase["type"] == "bookcase", "migrated: 005→bookcase")

container = next(o for o in w2["objects"] if o["id"] == "007")
check(container["type"] == "container", "migrated: 007→container")

door = next(o for o in w2["objects"] if o["id"] == "008")
check(door["type"] == "door", "migrated: 008→door")

# 检查 contains → state
b003 = next(s for s in s2["states"] if s["object_id"] == "003")
check(b003["contained_by"] == "007", "migrated: 003 contained_by=007")
check(b003["position"] is None, "migrated: 003 position=null (contained)")

b007 = next(s for s in s2["states"] if s["object_id"] == "007")
check("003" in b007["inventory"], "migrated: 007 inventory contains 003")

# 检查 position 迁移
b001 = next(s for s in s2["states"] if s["object_id"] == "001")
check(b001["position"] == [2.0, 0.0, 3.0], "migrated: 001 position intact")

# 检查 regions name→label
r_names = [r["name"] for r in w2["regions"]]
check("客厅" in r_names, "migrated: region 客厅 preserved")
check("书房" in r_names, "migrated: region 书房 preserved")

# 检查运时加载
with open("/tmp/test_mig_world.json", "w") as f:
    json.dump(w2, f, ensure_ascii=False, indent=2)
with open("/tmp/test_mig_state.json", "w") as f:
    json.dump(s2, f, ensure_ascii=False, indent=2)

db_mig = WorldDB()
db_mig.load("/tmp/test_mig_world.json", "/tmp/test_mig_state.json")
v_mig = db_mig.validate()
check(v_mig["errors"] == [], "migrated validate: 0 errors")
check(v_mig["warnings"] == [], "migrated validate: 0 warnings")
check(v_mig["passed"] == 8, "migrated validate: 8 passed")

api_mig = QueryAPI(db_mig)
check(api_mig.contained_by("003") == "007", "migrated runtime: 003 contained_by=007")
check(api_mig.inventory_of("007") == ["003"], "migrated runtime: 007 inventory=[003]")
check(api_mig.get_object("002")["type"] == "chair", "migrated runtime: 002 type=chair")

os.remove("/tmp/test_mig_world.json")
os.remove("/tmp/test_mig_state.json")

# ============================================================================
# 13. Observation v2
# ============================================================================
section("13. Observation v2")

from observation_builder import observe, format_observation_text

# 用独立 DB 设不同位置
db_obs = WorldDB()
db_obs.load("test_world_v2.json")
db_obs.set_state("chair_01", {"position": [2, 0, 3]})
db_obs.set_state("table_01", {"position": [4, 0, 1]})
db_obs.set_state("door_01", {"position": [0, 0, 5]})
db_obs.set_state("key_01", {"position": [6, 0, 0]})
db_obs.set_state("chest_01", {"position": [10, 0, 2]})
db_obs.set_state("lamp_01", {"position": [8, 0, 4]})

# 基本观察
obs = observe(db_obs, position=(3, 0, 2), radius=5)
check(len(obs["visible_objects"]) == 4, "observe r=5: 4 visible")
check(obs["radius"] == 5.0, "observe radius preserved")
check(obs["observer_position"]["x"] == 3.0, "observe pos.x preserved")

# 物体字段完整性
chair_v = next(o for o in obs["visible_objects"] if o["id"] == "chair_01")
check(chair_v["type"] == "chair", "observe: chair type preserved")
check(chair_v["label"] == "木椅", "observe: chair label preserved")
check(chair_v["distance"] > 0, "observe: distance > 0")
check(chair_v["contained_by"] is None, "observe: chair contained_by=None")
check(isinstance(chair_v["flags"], dict), "observe: flags is dict")
check(chair_v["region"] == "living_room", "observe: region preserved")

# 排序——按距离升序
for i in range(len(obs["visible_objects"]) - 1):
    check(obs["visible_objects"][i]["distance"] <= obs["visible_objects"][i+1]["distance"],
          f"observe: sorted by distance ({i})")

# 半径外不可见
obs_r3 = observe(db_obs, position=(3, 0, 2), radius=3)
check(len(obs_r3["visible_objects"]) == 2, "observe r=3: 2 visible (chair+table only)")

# contained_by 物体不可见——把 key 藏进 chest
db_obs.transfer("lamp_01", "chest_01", "key_01")
obs_hidden = observe(db_obs, position=(10, 0, 2), radius=5)
key_hidden = any(o["id"] == "key_01" for o in obs_hidden["visible_objects"])
check(not key_hidden, "observe: key hidden in chest → not visible")

# 拿出来后可见
db_obs.set_state("key_01", {"position": [10, 0, 3], "contained_by": None})
db_obs.set_state("chest_01", {"inventory": []})
obs_visible = observe(db_obs, position=(10, 0, 2), radius=5)
key_visible = any(o["id"] == "key_01" for o in obs_visible["visible_objects"])
check(key_visible, "observe: key taken out → visible")

# 没有 position 的物体不出现（纯 contained_by 状态）
db_obs.set_state("key_01", {"position": None, "contained_by": "chest_01"})
obs_nopos = observe(db_obs, position=(10, 0, 2), radius=10)
key_nopos = any(o["id"] == "key_01" for o in obs_nopos["visible_objects"])
check(not key_nopos, "observe: object w/o position not visible")

# 空场景
db_empty = WorldDB()
db_empty.load("test_world_v2.json")
for oid in list(db_empty.states.keys()):
    db_empty.set_state(oid, {"position": None, "contained_by": "void"})
obs_empty = observe(db_empty, position=(0, 0, 0), radius=100)
check(len(obs_empty["visible_objects"]) == 0, "observe: empty scene → 0 visible")

# format_observation_text
obs_text = format_observation_text(obs)
check("可见: 4" in obs_text, "format_text: 4 visible in text")
check("Observation @" in obs_text, "format_text: has header")

# ============================================================================
# 13b. FOV 视野锥
# ============================================================================
section("13b. FOV 视野锥")

# 独立 DB，避免受 Section 13 的状态污染
_db_fov = WorldDB()
_db_fov.load("test_world_v2.json")
_db_fov.set_state("chair_01", {"position": [2, 0, 3]})
_db_fov.set_state("table_01", {"position": [4, 0, 1]})
_db_fov.set_state("door_01", {"position": [0, 0, 5]})
_db_fov.set_state("key_01", {"position": [6, 0, 0]})
_db_fov.set_state("chest_01", {"position": [10, 0, 2]})
_db_fov.set_state("lamp_01", {"position": [8, 0, 4]})

# FOV-1: 不传 direction → 球形全向（兼容旧行为）
obs_fov1 = observe(_db_fov, position=(3, 0, 2), radius=5)
check(len(obs_fov1["visible_objects"]) == 4, "FOV: no direction → 4 visible")
check("direction" not in obs_fov1, "FOV: no direction in output")
check("fov_angle" not in obs_fov1, "FOV: no fov_angle in output")

# FOV-2: direction + fov_angle → FOV 模式
obs_fov2 = observe(_db_fov, position=(3, 0, 2), radius=5, direction=(1, 0, 0), fov_angle=90)
check(obs_fov2.get("direction") is not None, "FOV: direction in output")
check(obs_fov2.get("fov_angle") == 90, "FOV: fov_angle in output")

# FOV-3: FOV 90° → 只看正前方，看不到背后
ids90 = {o["id"] for o in obs_fov2["visible_objects"]}
check("table_01" in ids90, "FOV90: table visible (45° edge)")
check("key_01" in ids90, "FOV90: key visible (in front)")
check("chair_01" not in ids90, "FOV90: chair not visible (behind)")
check("door_01" not in ids90, "FOV90: door not visible (behind)")

# FOV-4: FOV 180° → 半球
obs_fov180 = observe(_db_fov, position=(3, 0, 2), radius=5, direction=(1, 0, 0), fov_angle=180)
ids180 = {o["id"] for o in obs_fov180["visible_objects"]}
check("chair_01" not in ids180, "FOV180: chair not visible (behind)")
check("key_01" in ids180, "FOV180: key visible")

# FOV-5: FOV 360° → 全向
obs_fov360 = observe(_db_fov, position=(3, 0, 2), radius=5, direction=(1, 0, 0), fov_angle=360)
check(len(obs_fov360["visible_objects"]) == 4, "FOV360: 4 visible (same as spherical)")

# FOV-6: 零长度方向向量 → 不崩
obs_fovz = observe(_db_fov, position=(3, 0, 2), radius=5, direction=(0, 0, 0), fov_angle=90)
check(isinstance(obs_fovz["visible_objects"], list), "FOV zero dir: no crash")

# FOV-7: 距离 + FOV 双重作用
obs_fov_far = observe(_db_fov, position=(3, 0, 2), radius=2, direction=(1, 0, 0), fov_angle=180)
check(len(obs_fov_far["visible_objects"]) >= 1, "FOV: distance + angle combined")

# FOV-8: 排序仍然按距离升序
for i in range(len(obs_fov180["visible_objects"]) - 1):
    check(obs_fov180["visible_objects"][i]["distance"] <= obs_fov180["visible_objects"][i+1]["distance"],
          f"FOV: sorted by distance ({i})")

# FOV-9: format_observation_text 显示 direction/fov
from observation_builder import format_observation_text as fmt_obs_fov
obs_fov_text = fmt_obs_fov(obs_fov180)
check("fov=" in obs_fov_text, "FOV format: shows fov=")

# FOV-10: 只传 direction 不传 fov → 保持全向
obs_onlydir = observe(_db_fov, position=(3, 0, 2), radius=5, direction=(1, 0, 0))
check(len(obs_onlydir["visible_objects"]) == 4, "FOV: direction without fov → 4 visible")

# ============================================================================
# 14. Agent Tool Adapter
# ============================================================================
section("14. Agent Tool Adapter")

from agent_adapter import WorldAPI, dispatch_tool, AGENT_TOOLS_SCHEMA

# 14a. 基本生命周期
api = WorldAPI()
check(api.load("test_world_v2.json"), "adapter: load ok")
v = api.validate()
check(v["errors"] == [], "adapter: validate clean")

# 设置一些初始状态
api.set_state("chair_01", {"position": [2, 0, 3]})
api.set_state("table_01", {"position": [4, 0, 1]})
api.set_state("door_01", {"position": [0, 0, 5]})
api.set_state("key_01", {"position": [6, 0, 0]})
api.set_state("chest_01", {"position": [10, 0, 2]})
api.set_state("lamp_01", {"position": [8, 0, 4]})

# 14b. observe
obs = api.observe((3, 0, 2), radius=5)
check(len(obs["visible_objects"]) == 4, "adapter observe: 4 visible")

# 14c. format_observation
text = api.format_observation(obs)
check("可见: 4" in text, "adapter format_obs: has count")

# 14d. get_object
obj = api.get_object("door_01")
check(obj is not None, "adapter get_object: not None")
check(obj["id"] == "door_01", "adapter get_object: id match")
check(api.get_object("nonexistent") is None, "adapter get_object: None for missing")

# 14e. get_state
st = api.get_state("door_01")
check(st is not None, "adapter get_state: not None")
check("position" in st, "adapter get_state: has position")
check("flags" in st, "adapter get_state: has flags")
check(api.get_state("nonexistent") is None, "adapter get_state: None for missing")

# 14f. objects_in_region
reg = api.objects_in_region("living_room")
check(len(reg) == 3, "adapter objects_in_region: 3 in living_room")
check(api.objects_in_region("nonexistent") == [], "adapter objects_in_region: [] missing")

# 14g. connected_regions
conn = api.connected_regions("living_room")
check(len(conn) == 2, "adapter connected_regions: 2 neighbors")

# 14h. related_objects
rels = api.related_objects("door_01")
check(len(rels) >= 1, "adapter related_objects: has results")
check(rels[0]["relation"]["type"] == "unlocks", "adapter related_objects: type=unlocks")
check("object" in rels[0], "adapter related_objects: has nested object")

# with filter
rels_f = api.related_objects("door_01", "unlocks")
check(len(rels_f) == 1, "adapter related_objects filter: 1")
rels_none = api.related_objects("door_01", "owns")
check(len(rels_none) == 0, "adapter related_objects filter: 0")

# 14i. container queries
check(api.contained_by("key_01") is None, "adapter contained_by: None (not in container)")
check(api.contained_by("nonexistent") is None, "adapter contained_by: None (missing)")
check(api.inventory_of("chest_01") == [], "adapter inventory_of: empty")
check(api.inventory_of("nonexistent") == [], "adapter inventory_of: [] missing")

# 14j. has_flag
check(api.has_flag("door_01", "open") == False, "adapter has_flag: door closed")
check(api.has_flag("door_01", "locked") == False, "adapter has_flag: door unlocked")
check(api.has_flag("nonexistent", "open") == False, "adapter has_flag: missing → False")

# 14k. template_of
tmpl = api.template_of("chair_01")
check(tmpl["interactions"] == ["sit"], "adapter template_of: sit")
check(api.template_of("nonexistent") is None, "adapter template_of: None missing")

# 14l. set_state
check(api.set_state("door_01", {"flags": {"open": True}}), "adapter set_state: ok")
check(api.has_flag("door_01", "open") == True, "adapter set_state: door now open")
check(not api.set_state("nonexistent", {"position": [0,0,0]}), "adapter set_state: False missing")

# 14m. transfer
api.set_state("lamp_01", {"inventory": ["key_01"]})
api.set_state("key_01", {"contained_by": "lamp_01", "position": None})
check(api.transfer("lamp_01", "chest_01", "key_01"), "adapter transfer: ok")
check(api.contained_by("key_01") == "chest_01", "adapter transfer: key in chest")
check(api.inventory_of("lamp_01") == [], "adapter transfer: lamp empty")
check(api.inventory_of("chest_01") == ["key_01"], "adapter transfer: chest has key")
check(not api.transfer("nonexistent", "chest_01", "key_01"), "adapter transfer: False missing")

# 14n. save
import tempfile
tmp_state = os.path.join(tempfile.gettempdir(), "test_agent_state.json")
check(api.save(state_path=tmp_state), "adapter save: ok")
check(os.path.exists(tmp_state), "adapter save: file exists")
os.remove(tmp_state)

# 14o. dispatch_tool — 测试 Agent 工具分发器
check(dispatch_tool(api, "observe", {"position": [3, 0, 2], "radius": 5})["ok"], "dispatch observe: ok")
check(dispatch_tool(api, "get_object", {"object_id": "door_01"})["ok"], "dispatch get_object: ok")
check(dispatch_tool(api, "has_flag", {"object_id": "door_01", "flag": "open"})["ok"], "dispatch has_flag: ok")
check(dispatch_tool(api, "get_object", {"object_id": "nonexistent"})["result"] is None, "dispatch get_object: result=None for missing")
check(not dispatch_tool(api, "unknown_tool", {})["ok"], "dispatch unknown: not ok")
check(dispatch_tool(api, "validate", {})["ok"], "dispatch validate: ok")

# 14p. AGENT_TOOLS_SCHEMA 完整性
check(len(AGENT_TOOLS_SCHEMA) == 12, "tools schema: 12 tools")
tool_names = {t["name"] for t in AGENT_TOOLS_SCHEMA}
check("observe" in tool_names, "tools schema: has observe")
check("set_state" in tool_names, "tools schema: has set_state")
check("transfer" in tool_names, "tools schema: has transfer")
check("get_object" in tool_names, "tools schema: has get_object")

# ============================================================================
# Summary
# ============================================================================
section("Summary")

print(f"\n  Total: {PASS} passed, {FAIL} failed  ({PASS + FAIL} checks)")
print()

# ============================================================================
# 15. Memory
# ============================================================================
section("15. Memory")

from memory import Memory

mem = Memory()

# 15a. 初始化
check(mem.discovered_objects() == [], "mem init: empty discovered")
check(mem.known_regions() == [], "mem init: empty regions")
check(mem.region_graph() == {}, "mem init: empty graph")
check(mem.agent_position() is None, "mem init: no position")

# 15b. 第一次观察
obs1 = {
    "observer_position": {"x": 3.0, "y": 0.0, "z": 2.0},
    "radius": 5.0,
    "visible_objects": [
        {"id": "chair_01", "label": "木椅", "type": "chair", "distance": 1.4,
         "position": [2, 0, 3], "flags": {}, "contained_by": None, "region": "living_room"},
        {"id": "table_01", "label": "茶几", "type": "table", "distance": 1.4,
         "position": [4, 0, 1], "flags": {}, "contained_by": None, "region": "living_room"},
    ],
    "timestamp": "2026-06-14T06:00:00Z",
}
mem.update_from_observation(obs1)

check(len(mem.discovered_objects()) == 2, "mem: discovered 2 objects")
check("chair_01" in mem.discovered_objects(), "mem: chair discovered")
check("table_01" in mem.discovered_objects(), "mem: table discovered")
check(mem.is_known("chair_01"), "mem: chair is known")
check(not mem.is_known("nonexistent"), "mem: unknown not known")
check(mem.agent_position() == (3.0, 0.0, 2.0), "mem: agent pos recorded")

# 15c. 区域发现
mem.update_region_graph("living_room", [
    {"id": "reg_002", "name": "bedroom", "label": "卧室", "via": "door_01"},
])
check("living_room" in mem.known_regions(), "mem: living_room known")
check("bedroom" in mem.known_regions(), "mem: bedroom known (from graph)")
check(mem.region_visited("living_room"), "mem: living_room visited")
check(mem.region_visited("bedroom"), "mem: bedroom visited")

# 15d. last_seen
chair_mem = mem.last_seen("chair_01")
check(chair_mem is not None, "mem last_seen: chair exists")
check(chair_mem["label"] == "木椅", "mem last_seen: label correct")
check(chair_mem["last_position"] == [2, 0, 3], "mem last_seen: position correct")
check(chair_mem["first_seen"] == "2026-06-14T06:00:00Z", "mem last_seen: first_seen")
check(not chair_mem["stale"], "mem last_seen: not stale")
check(mem.last_seen("nonexistent") is None, "mem last_seen: None for unknown")

# 15e. 第二次观察（椅子被移动了）
obs2 = {
    "observer_position": {"x": 3.0, "y": 0.0, "z": 2.0},
    "radius": 5.0,
    "visible_objects": [
        {"id": "chair_01", "label": "木椅", "type": "chair", "distance": 1.0,
         "position": [4, 0, 3], "flags": {}, "contained_by": None, "region": "living_room"},
    ],
    "timestamp": "2026-06-14T06:05:00Z",
}
mem.update_from_observation(obs2)

chair_mem2 = mem.last_seen("chair_01")
check(chair_mem2["last_position"] == [4, 0, 3], "mem: chair moved -> new position")
check(chair_mem2["first_seen"] == "2026-06-14T06:00:00Z", "mem: first_seen unchanged")
check(chair_mem2["last_seen"] == "2026-06-14T06:05:00Z", "mem: last_seen updated")
check(not chair_mem2["stale"], "mem: still not stale (just observed)")

# 15f. mark_stale
mem.mark_stale("chair_01")
check(mem.last_seen("chair_01")["stale"], "mem: chair now stale")
check(len(mem.stale_objects()) == 1, "mem: 1 stale object")
check(mem.stale_objects() == ["chair_01"], "mem: stale list correct")

# 标记没见过的不炸
mem.mark_stale("nonexistent")
check(len(mem.stale_objects()) == 1, "mem: marking unknown does nothing")

# 重新观察 -> unmark stale
mem.update_from_observation(obs2)
check(not mem.last_seen("chair_01")["stale"], "mem: re-observed -> not stale")

# 15g. update_state_change
mem.update_state_change("door_01", {
    "position": [0, 0, 5], "flags": {"open": True}, "contained_by": None,
})
check(mem.is_known("door_01"), "mem: door now known (via state change)")
check(mem.last_seen("door_01")["last_position"] == [0, 0, 5], "mem: door position from state change")

# 15h. summary
s = mem.summary()
check(isinstance(s, dict), "mem summary: is dict")
check(s["total_discovered"] >= 3, "mem summary: at least 3 discovered")
check(isinstance(s["known_regions"], int), "mem summary: region count")

# 15i. 保存/加载
import tempfile as _tmpf, os as _osf
tmp_mem = _osf.path.join(_tmpf.gettempdir(), "test_memory_runtime.json")
mem.save(tmp_mem)
check(_osf.path.exists(tmp_mem), "mem save: file exists")

mem2 = Memory()
mem2.load(tmp_mem)
check(mem2.is_known("chair_01"), "mem load: chair remembered")
check(mem2.is_known("table_01"), "mem load: table remembered")
check("living_room" in mem2.known_regions(), "mem load: region remembered")
check(mem2.agent_position() == (3.0, 0.0, 2.0), "mem load: position restored")
_osf.remove(tmp_mem)

# 15j. region_graph
g = mem.region_graph()
check("living_room" in g, "mem graph: has living_room")
check("bedroom" in g["living_room"], "mem graph: living_room<->bedroom")

# 15k. 第二次区域图更新（同区域新邻居）
mem.update_region_graph("living_room", [
    {"id": "reg_002", "name": "bedroom", "label": "卧室", "via": "door_01"},
    {"id": "reg_003", "name": "entrance", "label": "入口", "via": None},
])
g2 = mem.region_graph()
check(len(g2.get("living_room", [])) == 2, "mem graph: 2 neighbors after update")




# ============================================================================
# 16. Agent Loop（框架测试，不依赖 LLM）
# ============================================================================
section("16. Agent Loop")

from agent_loop import AgentLoop, SYSTEM_PROMPT
from memory import Memory as MemForLoop

# 独立 API + Memory（不污染前面的状态）
_api_loop = WorldDB()
_api_loop.load("test_world_v2.json")
_api_loop.set_state("chair_01", {"position": [2, 0, 3]})
_api_loop.set_state("table_01", {"position": [4, 0, 1]})
_api_loop.set_state("door_01", {"position": [0, 0, 5], "flags": {"open": False, "locked": False}})
_api_loop.set_state("key_01", {"position": [6, 0, 0]})
_api_loop.set_state("chest_01", {"position": [10, 0, 2]})
_api_loop.set_state("lamp_01", {"position": [8, 0, 4]})

from agent_adapter import WorldAPI as WAPI
_loop_api = WAPI("test_world_v2.json")
_loop_api._db = _api_loop  # 替换为预制 DB
from world_db_v2 import QueryAPI
_loop_api._query = QueryAPI(_api_loop)

_loop_mem = MemForLoop()
loop = AgentLoop(_loop_api, _loop_mem, goal="找到钥匙，打开门", verbose=False)

# 16a. 初始化
check(loop.goal == "找到钥匙，打开门", "loop init: goal")
check(loop._tool_call_count == 0, "loop init: no calls yet")
check(not loop._done, "loop init: not done")
check(isinstance(SYSTEM_PROMPT, str), "loop: system prompt is string")
check("observe" in SYSTEM_PROMPT, "loop: system prompt has observe")

# 16b. parse_tool_call
check(loop._parse_tool_call("垃圾") is None, "loop parse: garbage -> None")
tc = loop._parse_tool_call('{"tool": "observe", "arguments": {"position": [0,0,0]}}')
check(tc is not None, "loop parse: valid tool call")
check(tc["tool"] == "observe", "loop parse: tool name")
tc_done = loop._parse_tool_call('{"done": true, "summary": "完成了"}')
check(tc_done is not None, "loop parse: done signal")
check(tc_done["done"] == True, "loop parse: done=true")
# markdown code block
tc_md = loop._parse_tool_call('```json\n{"tool": "get_object", "arguments": {"object_id": "key_01"}}\n```')
check(tc_md is not None, "loop parse: markdown block")
check(tc_md["tool"] == "get_object", "loop parse: markdown tool name")

# 16c. _describe_visible
obs_test = {
    "radius": 5.0,
    "visible_objects": [
        {"id": "door_01", "label": "大门", "type": "door", "distance": 2.0,
         "flags": {"open": False, "locked": False}, "region": "entrance"},
    ],
}
desc = loop._describe_visible(obs_test)
check("door_01" in desc, "loop describe: has door id")
check("2.0m" in desc, "loop describe: has distance")
check("entrance" in desc, "loop describe: has region")
# flags: open=False so not shown in active flags
check("door" in desc, "loop describe: has door in desc")

# 16d. _describe_visible empty
obs_empty = {"radius": 5.0, "visible_objects": []}
desc_empty = loop._describe_visible(obs_empty)
check("空无一物" in desc_empty, "loop describe empty: has empty text")

# 16e. _format_result
check(loop._format_result("set_state", True) == "True", "loop fmt: bool True")
check(loop._format_result("get_object", None) == "None", "loop fmt: None")
check("个可见物体" in loop._format_result("observe", {"visible_objects": [{}, {}]}), "loop fmt: observe count")
check("个结果" in loop._format_result("objects_in_region", [{}, {}]), "loop fmt: list count")

# 16f. _first_observe（不依赖 LLM）
obs_result = loop._first_observe()
check(not obs_result["done"], "loop first_observe: not done")
check("observation" in obs_result, "loop first_observe: has observation")
check(len(loop._messages) >= 2, "loop first_observe: messages initialized")
check(loop._tool_call_count == 1, "loop first_observe: call count=1")
check(_loop_mem.discovered_objects() != [], "loop first_observe: memory updated")

# 16g. _update_memory_from_action
_loop_mem2 = MemForLoop()
loop2 = AgentLoop(_loop_api, _loop_mem2, goal="test", verbose=False)

# 模拟 get_state 更新记忆
loop2._update_memory_from_action("get_state", {"object_id": "door_01"}, {
    "ok": True, "result": {"position": [0, 0, 5], "flags": {"open": True}, "contained_by": None},
})
check(_loop_mem2.is_known("door_01"), "loop memory: door known after get_state")
check(_loop_mem2.last_seen("door_01")["last_position"] == [0, 0, 5], "loop memory: door state recorded")

# 模拟 set_state 更新记忆（先设 door 为 open）
_loop_api.set_state("door_01", {"flags": {"open": True}})
loop2._update_memory_from_action("set_state", {"object_id": "door_01"}, {
    "ok": True, "result": True,
})
check(_loop_mem2.last_seen("door_01")["last_flags"].get("open") == True, "loop memory: set_state updates flags")

# 16h. 失败工具调用不更新记忆
_loop_mem3 = MemForLoop()
loop3 = AgentLoop(_loop_api, _loop_mem3, goal="test", verbose=False)
loop3._update_memory_from_action("get_object", {"object_id": "nonexist"}, {
    "ok": False, "result": None, "error": "not found",
})
check(not _loop_mem3.is_known("nonexist"), "loop memory: failed call does not record")

if FAIL == 0:
    print("  🎉 All tests passed!")
else:
    print(f"  💥 {FAIL} tests FAILED!")
    sys.exit(1)
