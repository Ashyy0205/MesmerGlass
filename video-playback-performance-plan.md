# Video Playback Performance Plan (FPS + Hitching)

Date: 2026-01-20

## Goal
Eliminate compositor hitching and sustained FPS drops when:
- Switching into a video playback
- Playing any video playback continuously
- Fast-cycling videos (rapid theme/video changes)

This plan focuses on the current code path:
- Decoder / buffering: `mesmerglass/content/video.py` (`VideoDecoder`, `VideoStreamer`)
- Simple wrapper used by ThemeBank: `mesmerglass/content/simple_video_streamer.py` (`SimpleVideoStreamer`)
- Orchestration + upload decisions: `mesmerglass/mesmerloom/visual_director.py` (`VisualDirector`)
- OpenGL upload + fade behavior: `mesmerglass/mesmerloom/compositor.py` (`LoomCompositor.set_background_video_frame`)

Related docs to cross-check:
- `docs/technical/video-engine.md`
- `docs/technical/image-video-loading.md`

## Current Behavior (Observed)
### Symptoms
1) **Switch spike**: noticeable FPS dip right when a new video is selected.
2) **Sustained lower FPS**: compositor hitches throughout video playback.
3) **Fast cycling** (rapid video changes) magnifies hitching and makes overall compositor FPS unstable.

### Why this can happen with the current design
There are two main classes of cost:

1) **CPU-side decode / I/O stalls**
- `VisualDirector._on_change_video()` calls `video_streamer.load_video(path)` synchronously.
- `VideoStreamer.load_video()` constructs `VideoDecoder(path)` which opens `cv2.VideoCapture(path)`.
- Even with a prefill budget, the *open* + initial decode can block the UI thread.

2) **GPU-side frame upload churn**
- `VisualDirector.update()` fetches a frame and uploads it to compositor(s).
- The compositor uploads RGB data using `glTex(Sub)Image2D`.
- On `new_video=True`, we may force texture recreation (and maintain a fade queue), which is expensive.

A key point: **even if decode is perfectly async**, sustained low FPS can still happen if we are uploading full frames too often (e.g., uploading the same frame 60 times/sec while the video effectively advances ~15 frames/sec).

## Where to Measure (before/after)
### Built-in logs to look for
`VisualDirector` already emits perf logs when thresholds are exceeded:
- `[visual.perf] video.load took …ms` (switch spike)
- `[visual.perf] Video streamer update took …ms` (decode/buffer)
- `[visual.perf] Video frame fetch took …ms` (frame access)
- `[visual.perf] Video frame upload took …ms` (OpenGL upload)
- `[visual.perf] Entire video tick took …ms` (overall per-tick budget)

### Add/confirm these metrics (if needed)
- Average and P95 upload time when video is playing
- Upload count per second while video is playing
- “first-frame” upload timing on video changes
- Video decode cadence (buffer fill rate)

### Acceptance targets
- During steady-state video playback: avoid frequent spikes > 10–16ms in the render path.
- During fast cycling: no repeated large spikes caused by texture reallocation.
- Subjective: video playback should look smooth; compositor should remain responsive.

## Hypotheses (Root Causes)
### A) Uploading unchanged frames every compositor tick
- `SimpleVideoStreamer.update()` advances video at an effective target ~15fps.
- The compositor can run at ~60fps.
- If `VisualDirector` uploads every tick regardless of whether the frame changed:
  - We can do **4× redundant uploads**, which can tank FPS.

### B) Texture recreation and fade queue churn on frequent video changes
- On the first frame of a new video, `new_video=True` may:
  - Push the previous texture into a fade queue
  - Force creation of a new texture so we don’t overwrite the old one
- When fast-cycling videos, this creates repeated allocation/deallocation pressure and extra GPU work.

### C) Decoder open + initial decode is synchronous
- OpenCV’s `VideoCapture` open can stall and is not protected by the prefill budget.
- This contributes to switching spikes.

## Proposed Improvements (Phased)

### Phase 1 (Quick Win): Upload-on-change (Dedupe uploads)
**Objective:** Fix sustained low FPS by eliminating redundant GPU uploads.

**Design:** Only call `set_background_video_frame()` when a *new* frame is available.

Implementation outline:
- In `VisualDirector.update()` (video tick block):
  - Track an identifier for the current frame (preferably a monotonic frame index or frame timestamp).
  - If the identifier is unchanged since last upload, skip uploading.
  - Always allow upload for:
    - the first frame after a video load (`_video_first_frame`), or
    - resolution changes.

Where to store “last uploaded frame id”:
- `VisualDirector` fields, e.g.:
  - `_last_uploaded_video_path: Optional[Path]`
  - `_last_uploaded_video_frame_id: Optional[float|int]`

How to get a stable frame id:
- Option A (best): extend `SimpleVideoStreamer` / `VideoStreamer` to expose `current_frame_idx`.
- Option B: use `VideoFrame.timestamp` (already computed) — careful: timestamp is derived from decoder FPS and local counters; ensure it changes per frame.

Success criteria:
- Upload count drops from ~60/s to ~15/s (or whatever target FPS is).
- `[visual.perf] Video frame upload …` warnings become rare.

Risk:
- If frame-id logic is wrong, video may appear to “freeze” (because we skip needed uploads). Mitigation: fall back to uploading at least every N ticks if uncertain.

---

### Phase 2 (Quick/Medium): Reduce texture churn on video switches
**Objective:** Fix hitching during fast cycling and reduce first-frame stalls.

**Design options:**
1) **Two persistent textures (front/back)**
   - Maintain `video_tex_front` and `video_tex_back`.
   - On new video:
     - Upload first frame into the back texture.
     - Fade between front/back in shader or via a small queue.
     - Swap references when fade completes.
   - Avoid `glDeleteTextures`/`glGenTextures` per switch.

2) **Persistent single texture + separate “fade snapshot”**
   - Keep one persistent video texture that always receives updates.
   - When switching, capture the old texture content into a second texture once (or keep the old one alive) for the fade.
   - Only allocate when resolution changes.

Implementation likely lives in:
- `LoomCompositor.set_background_video_frame()` and `_render_background()`.

Success criteria:
- Rapid video changes no longer cause repeated `glTexImage2D` allocations.
- Noticeably fewer hitch spikes when cycling.

---

### Phase 3 (Medium): Make video load/open async (switch spikes)
**Objective:** Remove UI-thread stalls during `VideoCapture.open()` and initial decode.

Current issue:
- `VideoStreamer.load_video()` builds `VideoDecoder(path)` on the caller thread.

Target design:
- “Request video change” enqueues a background job:
  - Open decoder
  - Decode until at least 1–N frames are ready
- UI thread continues rendering old media.
- Once ready, atomically swap streamer state and mark `_video_first_frame=True`.

Implementation sketch:
- Add an async “load request” API:
  - `VideoStreamer.request_video(path)` / `poll_ready()`
  - or `SimpleVideoStreamer.load_video_async(...)`
- Or reuse existing `_next` buffer in `VideoStreamer` properly:
  - preload into `_next`
  - swap when safe

Success criteria:
- `video.load` spikes drop substantially.
- Switching feels smooth even with slower storage or large files.

---

### Phase 4 (Optional / Longer-term): Decoder improvements
**Objective:** Further reduce decode cost and jitter.

Options:
- Replace/augment OpenCV decode with PyAV
- Investigate hardware decode (NVDEC) where feasible
- Consider decoding to a GPU-friendly pixel format and avoid expensive conversions

This phase has higher scope and packaging implications.

## Implementation Checklist (Concrete Tasks)

### A) Upload-on-change
- [ ] Add “frame-id” tracking to `VisualDirector`.
- [ ] Ensure we skip upload when frame-id hasn’t changed.
- [ ] Add debug counter: `video_uploads_per_second` (throttled log).
- [ ] Verify behavior with:
  - steady-state video
  - rapid video cycling
  - multiple compositors (secondary mirrors)

### B) Texture churn reduction
- [ ] Refactor compositor video texture handling to avoid delete/regenerate on switch.
- [ ] Validate fade still works (or re-implement fade in a stable way).
- [ ] Add logs for texture allocations (throttled) and queue growth.

### C) Async load
- [ ] Introduce async open/decode for new videos.
- [ ] Ensure thread safety for frame buffers.
- [ ] Provide “ready” handshake so we only swap once first frame exists.

## Testing / Verification Plan
Manual scenarios:
1) Load a cuelist with a video cue; observe steady FPS for 30–60s.
2) Fast cycle videos (themebank selection changes quickly).
3) Switch between image-only and video-only playbacks repeatedly.
4) Multi-display compositors active (primary + secondary) to ensure upload cost doesn’t multiply unexpectedly.

Diagnostics:
- Compare perf logs before/after.
- Confirm upload rate matches target video FPS (not compositor FPS).

## Notes / Config Knobs
These already exist and may be useful during experiments:
- `MESMERGLASS_VIDEO_PREFILL_FRAMES` (default seen: 48 in code; app constructs `SimpleVideoStreamer(... prefill_frames=24)`)
- `MESMERGLASS_VIDEO_PREFILL_MAX_MS` (default 12ms)

If debugging:
- Temporarily lower `prefill_frames` and/or `prefill max ms` to reduce switch stalls.
- Add a flag to force video upload every N frames to isolate whether “skip uploads” logic is correct.

---

## Proposed Order of Attack
1) Phase 1 (Upload-on-change) — fastest, biggest sustained-FPS win.
2) Phase 2 (Texture churn reduction) — biggest win for fast cycling.
3) Phase 3 (Async open/decode) — biggest win for switch spikes.
4) Phase 4 (Decoder swap/hardware decode) — optional optimization layer.
