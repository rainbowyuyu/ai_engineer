# Oil Motion · The AI Engineer

Scroll-scrub baked-video homepage for BESO / The AI Engineer.
At the end of the scrub, the landing LLM chat workbench takes over.

## Four facts

| File | Role |
|------|------|
| `source/concept-contract.yaml` | User intent |
| `source/motion-brief.yaml` | Production plan |
| `build/timeline.json` | Compiled timeline |
| `build/motion-budget.json` | Delivery + controller |

## Reproduce

```bash
# Proxy (蓝海加速 · 规则模式常见本地端口)
export HTTPS_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=http://127.0.0.1:7897

OIL_MOTION="$HOME/.cursor/skills/oil-motion"   # Windows: %USERPROFILE%\.cursor\skills\oil-motion
python "$OIL_MOTION/scripts/oil_motion_config.py" status

# Keyframes 16:9
python "$OIL_MOTION/scripts/image_job.py" --prompt-file source/prompts/K0.txt \
  --output source/keyframes/K0.png --size 1792x1024 --no-transparent --force
# … K1–K6 …

# Budget
python "$OIL_MOTION/scripts/motion_budget.py" \
  --frames 315 --display 1440x810 --dpr 2 \
  --driver scroll --parameter-space linear --time-control scrub \
  --access sequential --background-owner video \
  --scroll-pages 6 --frames-per-page 45 \
  --report build/motion-budget.json --strict --json
```

Pilot master: `pilot/source_master.mp4` (all-intra H.264 from keyframe holds + crossfades).  
Final: `final/desktop.mp4`, `final/mobile.mp4`, `final/poster.png`.

## Runtime

`frontend_static/flow_main.oilIntro.js` mounts before `.app`, scrub-maps scroll → `video.currentTime`, then focuses `#landingComposerDock`.

- Skip: `?intro=0`
- Force: `?intro=1`
