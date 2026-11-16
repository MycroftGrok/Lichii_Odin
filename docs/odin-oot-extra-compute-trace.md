# Ocarina of Time: post-HMMA 4 FPS stutter — second compute shader trace

This is a **diagnostics-only** branch based on the verified 16 FPS experimental
HMMA workgroup-memory build (`ce91379dca0c714cfd236eb7f3a5a58b7550c2f7`).
The proven opt-in optimization is preserved; no more shaders are substituted.

## Measured evidence (Odin 3 Ultra, Fedora 44 ArmadaOS, Turnip, 2026-11-16)

Source: user's `eden-oot-hmma-full.log` captured through
`oot-low-demand.sh --hmma-lds --profile`.

- Shader `03bf0ffc7d2d0bed`: old ~368 ms, with HMMA LDS typically 28-34 ms,
  workgroup 128x1x1, dispatch 43x24x1, 192 tensor instructions,
  workgroup shared memory raised from 5120 to 12288 bytes.
- Shader `e40f5efb5480e692`: **351.306 ms** once in the early game transition,
  dispatch 30x34x1. Tensor instruction count/guest native key unknown.
- Shader `9302bc0d6d1d9bc1`: **231.024 ms** once at GPU
  frame 9863 with 267.413 ms frame span, dispatch 40x23x1. Tensor instruction
  count/guest native key unknown; plausibly corresponds to a brief 4 FPS dip.
- Subsequent ordinary gameplay: ~65-70 ms GPU frames / approximately 16 FPS,
  with 30-32 ms from the known HMMA shader.
- Initial transition also built 300 runtime pipelines in one reporting interval,
  and another 60 in a later one; compilation causes additional stutters.
  Per-game Precache shaders=Always and Build all cached shaders=true were
  already enabled in the log. The HMMA build's separate cache was initially
  almost empty, so the first run compiled many new pipelines.

## Next information needed

When explicit `--hmma-lds --profile` is selected, capture the **three exact
hashes** as SPIR-V in `~/.local/share/lichii/dump`, plus IR workgroup/shared
memory/storage buffer counts, HMMA/TensorMulAdd instruction count split by K=8
and K=16, and the first eight native dispatches of each hash. This identifies
whether the original optimization can be safely adapted to another shader;
**do not broaden the LDS substitution just from a similar dispatch grid**.

To avoid overwriting or affecting caches from the proven experimental build,
this branch uses `XDG_CACHE_HOME=~/.cache/lichii-oot-extra-compute-trace-v2`
only when `--hmma-lds` is selected. No cache is deleted.

After normal Lichii shutdown, a diagnostic ZIP containing the log and any
captured `.spv` files is saved to `~/Downloads/oot-extra-compute-trace-*.zip`.
Upload the ZIP for analysis. This trace **does not claim to reduce the 4 FPS dip**.

Command inside the existing `lichii-debug` toolbox, once the branch's
separately packaged ARM64 experimental build succeeds:

```bash
bash "$HOME/Applications/Lichii/test-builds/oot-extra-compute-<sha>/lichii/usr/bin/oot-low-demand.sh" --hmma-lds --profile
```

Only test at the currently reachable Deku Tree/Navi opening; do not assume
the game can reach further scenes. The stable Lichii binary, saves and ROMs
must remain untouched.
