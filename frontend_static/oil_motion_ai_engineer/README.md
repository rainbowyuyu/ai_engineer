# Oil Motion · The AI Engineer

Archived scroll-scrub cinematic paper workflow for BESO / The AI Engineer.
The production landing page no longer mounts this opening animation.

## Four facts

| File | Role |
|------|------|
| `source/concept-contract.yaml` | User intent |
| `source/motion-brief.yaml` | Production plan |
| `build/timeline.json` | Compiled timeline |
| `build/motion-budget.json` | Delivery + controller |

## Reproduce

```bash
# Compile paper-grounded keyframes and the all-intra scrub master.
python scripts/bake_oil_intro_project_video.py

# The compiler uses the paper-associated FOWT renders in docs/assets and
# writes content-only frames to source/keyframes_scroll/.

# Budget
python "$OIL_MOTION/scripts/motion_budget.py" \
  --frames 668 --display 1440x810 --dpr 1 \
  --driver scroll --parameter-space linear --time-control scrub \
  --access sequential --background-owner video \
  --scroll-pages 6.2 --frames-per-page 24 \
  --report build/motion-budget.json --strict --json
```

Pilot master: `pilot/source_master_scroll.mp4` (all-intra H.264 from keyframe holds + crossfades).
Final: `final/desktop_scroll.mp4`, `final/mobile_scroll.mp4`, `final/poster_scroll.png`.

## Runtime

The original runtime controller has been removed from the landing page. The
project files remain here only as an archive for reproducibility.
