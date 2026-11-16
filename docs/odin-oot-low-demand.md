# Odin 3 Ultra / ArmadaOS: Ocarina of Time low-demand A/B profile

Experimental branch `experiment/odin3-oot-low-demand`. Target title
`0400486024DEC000`; keep your existing game files and saves unchanged.

## Why this profile

The repeated 3 FPS measurement in the Deku Tree conversation is associated with
one compute shader `03bf0ffc7d2d0bed`: approximately 368-377 ms at grid
`43x24x1`, dominating the real GPU work and generating ~380 ms read-back
fence waits. Shader compilation, mesh fallback and CPU backend changes did not
resolve it. This build captures just that shader when profiling is enabled.

Banana Native's Android OOT *Performance* profile renders a 720p window with
~540p scene, disables Full vegetation and leaves Max Resolution and Texture Pool
x2 disabled. That configuration and its game patches are not Lichii patches.
Our ARM64 profile is a conservative approximation; it has **not** been
benchmarked as playable on Odin/Turnip.

## What EDEN_NX2_OOT_LOW_DEMAND=1 changes (only Ocarina)

1. Disables the built-in *Max Resolution* patch at runtime so the game's own
   dynamic-resolution path may work. Does not modify saved Add-On choices.
2. Disables the built-in *Texture Pool x2* patch at runtime, reducing the
   preallocated graphics pool, where the supported game revision matches.
3. Enables the existing **No sharpening** path that copies the tonemapped
   scene instead of using the game's sharpening network when the replacement
   passes its safety checks.
4. Suppresses temporal FSR/DLSS substitution for Ocarina; preserves user
   settings and reverts when launched without the flag.
5. Leaves Dynamic FPS, controller mapping, Steam artwork, saves, firmware and
   the OS Mesa driver unchanged.

The Lichii graphics UI still controls display mode/resolution. For the
*first* comparable run choose **Handheld (720p)** and **1X resolution** in
Ocarina's per-game settings, Vulkan, NCE and a 30 FPS cap if available. Avoid
further downscaling until the initial run is stable: Lichii's 1/2X scaling is
not identical to Banana Native's fixed ~540p internal render. A 30 FPS cap is
for pacing and battery, not a fix for 370 ms GPU execution. Lichii does not
yet port Banana Native's vegetation/distance game patch for this title.

If the game uses an unrecognized revision, the guarded NSO patch exclusions may
have no effect. Read the internal log and verify which patches were applied.

## Launcher

Extract the *experimental* native ARM64 tar.gz into an **unused test directory**,
not over the released Lichii installation. The package includes
`lichii/usr/bin/oot-low-demand.sh`.

From inside the `lichii-debug` Toolbox, run:

```bash
bash "/path/to/extracted/lichii/usr/bin/oot-low-demand.sh" --profile
```

The launcher finds the adjacent Lichii binary, forces the system Mesa Turnip
ICD for that process and sets the title-specific low-demand mode. Profiling
saves a copy of the emulator log under
`~/Development/turnip-a830-drm/oot-low-demand-profiles/`.
For true FPS comparisons without timestamp overhead, omit `--profile`.

`--aggressive` additionally sets `EDEN_NX2_OOT_SKIP_UNUSED_HEAVY=1`:
it attempts to skip **only** native program key `d9ee412f00ce399a`
after the existing No sharpening bypass has replaced the output pass. The
effect is **not proven on Odin**, may introduce visual corruption, and is
not enabled by default. The 370 ms SPIR-V hash has not yet been verified
to map to that native key. Do not interpret a zero impact as proof either
way; collect the targeted compute trace first.

If you run the script from a separate source checkout, set
`LICHII_EXPERIMENT_BIN` to the extracted experimental executable.
Never run this launcher against a release binary expecting these flags
to exist in its source.

## What to compare

In the **same Deku Tree / Navi conversation**, allow 30 seconds of stable
gameplay and record actual FPS. Test baseline Build 2 and this experimental
profile independently under system Turnip. Compare `DKB gpu_work`
for shader `03bf0ffc7d2d0bed`, actual Vulkan GPU time, and read-back waits.
Normal performance comparison should use the same trace flags in both builds
or neither; timestamp tracing adds overhead.

The captured SPIR-V file is placed in Lichii's regular dump directory
(`<titleID>_03bf0ffc7d2d0bed.spv`), and can be analyzed with `spirv-dis`
and `spirv-val`. **Do not** distribute game assets or guest shader binaries.

No code in this profile resets shader caches, deletes game data, changes
an OS driver, or replaces the user's normal Lichii executable.
