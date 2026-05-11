---
name: cad
description: 文本转 CAD（build123d / STEP-first）。本仓库内嵌完整技能于 third_party/text-to-cad/cad_skill；与 Qwen 侧栏工具 cad_skill_help、cad_skill_step 对齐。
---

# 在 beso_ai 中使用

- **完整正文与引用**：打开仓库内  
  `third_party/text-to-cad/cad_skill/SKILL.md`  
  及同目录 `references/*.md`。
- **命令行（与上游一致）**：在 `third_party/text-to-cad/cad_skill` 下执行  
  `python -m scripts.step <生成器.py>`（需 `PYTHONPATH` 包含该 `cad_skill` 目录，或见 `third_party/text-to-cad/README.md`）。
- **Web 侧栏助手**：开启「工具」后，模型可调用 `cad_skill_help` / `cad_skill_step`，无需用户手写 JSON 规格；STEP 为首要产物。
