# Odin 3 Ultra Ocarina: dual-HMMA LDS experimental A/B

## Measurements and motivation (2026-11-16)

**Known working performance baseline:** Native AArch64 ArmadaOS/Turnip Lichii
with `--hmma-lds` optimizing exactly one Ocarina program:
`03bf0ffc7d2d0bed`, native key `d8efd9f0c95abd80`, 192 HMMA
K=16 operations, 128 threads, 5120 guest shared bytes, 43x24x1
grid, reduced shader GPU time from ~368 ms to ~30-32 ms; user
observed ~16 FPS (sometimes ~4 FPS stutters) at the initial Deku
Tree/Navi dialogue. Do not claim later gameplay is playable.

Additional uploaded diagnostic ZIP `oot-extra-compute-trace-20261116-171948.zip`
captured a new compute shader:
- SPIR-V `e40f5efb5480e692`, native key `6f9367bd41dc0b58`,
  grid **30x34x1**, workgroup **128x1x1**, guest shared **5632B**,
  **176 TensorMulAdd K=16 instructions**, no K=8, **1 SSBO**,
  no global memory, original SPIR-V **213740 bytes**.
- GPU executions **333.390, 333.948, 334.857, 336.622 ms**.
- Earlier shader `9302bc0d6d1d9bc1` (~231 ms) did not run in this
  particular test and was not captured. Its native key and IR signature
  are unknown. Do not extend to it without direct capture.

## Experimental change (unverified)

When enabled with `EDEN_NX2_OOT_HMMA_LDS=1`, Lichii now attempts
the same existing subgroup shared-memory HMMA substitution on both
*exact observed* IR signatures:

1. 192 HMMA ops + 5120B guest workgroup memory (previously tested)
2. 176 HMMA ops + 5632B guest workgroup memory (**new**)

For either, require title ID `0400486024DEC000`, compute stage,
128x1x1 threads, a single SSBO, no global memory, 16-step HMMA
only, supported subgroups, and shared-memory total fitting the
driver's maximum capped to 32KiB. The new shader needs
5632+((128+128)*7*4)=**12800 shared bytes** as estimated by the
emitter. Both other games and non-HMMA runs remain unchanged.

The launcher isolates new compiled shaders in
`~/.cache/lichii-oot-dual-hmma-lds-v3` to preserve the prior
16 FPS shader cache. It also retains original SPIR-V captures when
available; never delete caches to force this experiment.

The source is for an incremental **local** Fedora 44 aarch64 build
inside existing `lichii-debug`. The user keeps all stable binaries,
saves, ROMs, Steam artwork/configuration and prior HMMA builds.
Prefer `cmake --build ... --target lichii --parallel 4` in the existing
isolated `~/Applications/Lichii/local-builds/oot-extra-compute/build`
after safely fetching/switching this Git branch. Keep a backup copy
of that prior local *diagnostic* binary before recompiling.

Run `--hmma-lds --profile` once and verify **two** log lines
`OOT HMMA LDS enabled`, one with `tensor_ops=192 guest_shared=5120`
and another with `tensor_ops=176 guest_shared=5632`. If the
second signature does not match, do not claim optimization active.
After the shader's next use, compare time for
`s6:e40f5efb5480e692` to ~334ms baseline. Monitor rendering
correctness and do not infer later-scene correctness.

**Status:** source change only, not yet compiled or gameplay validated.
The older 16 FPS package remains the known working fallback.
