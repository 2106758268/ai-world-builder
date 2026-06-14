# AI World Builder

> 🏗️ 将 Blender 3D 场景转化为 AI 可理解的世界数据库

## 这是什么？

AI World Builder 是一个 **Blender 5.0 插件**。它能：

- 🏷️ **给 3D 物体打标签**——在 Blender 里给 mesh 物体标注类型、属性、行为
- 🗺️ **按区域组织场景**——创建区域（如"客厅""卧室"），物体自动归类
- 🔗 **建立物体关系**——标记物体之间的连接、包含、触发等关系
- 👁️ **模拟 AI 观察**——以任意坐标和半径"看"场景，支持 FOV 视野锥
- 📤 **导出世界数据**——生成 AI 可读的 `world.json`

## 安装

1. 下载 `ai_world_builder.py`、`observation_builder.py`、`world_db.py`
2. 放到 Blender addons 目录：
   - Windows: `%APPDATA%\Blender Foundation\Blender\5.0\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/5.0/scripts/addons/`
   - Linux: `~/.config/blender/5.0/scripts/addons/`
3. Blender → Edit → Preferences → Add-ons → 搜索 "World Builder" → 启用

## 文件结构

```
ai_world_builder.py      # 主插件 — Blender UI 面板、标注、区域、关系管理
observation_builder.py   # 观察引擎 — 视野计算、距离排序、FOV 裁剪
world_db.py              # 世界数据库 — 导入/导出、查询、验证
test_runtime.py          # 离线测试
docs/                    # 设计文档
test_world.json          # 测试数据
```

## 快速开始

1. **标注物体**：选中 mesh → 右侧 World Builder 面板 → 设置类型、标签
2. **创建区域**：高级管理 → Region Topology → 输入名称 → `+`
3. **物体归入区域**：在 Main 面板里选区域
4. **观察**：Observation 面板 → 设置位置/半径 → 「从场景观察」
5. **导出**：World Status 面板 → 导出 world.json

## 数据持久化

插件会在 `.blend` 文件同目录生成 `.awb_world_data.json`，自动保存区域拓扑和物体关系。打开旧文件时自动恢复。

## 开发

```bash
# 运行测试
python test_runtime.py
```

## 版本

`0.12.0` — Blender 5.0

## 作者

[终](https://github.com/) & 云袖 ☁️
