# Handheld hardware detection and controller routing (experimental)

**Status:** feature branch only; needs native AArch64 compilation and actual controller
tests on Odin 3 Ultra. Do not merge into the working Steam-menu preview until verified.

## Data model

`src/yuzu/handheld_catalog.json` is a versioned, packaged Qt resource:

`chipsets[] -> handhelds[] -> models[]`

Each family has multiple machine/controller aliases, an explicit manufacturer, and
manufacturer-named model variants with nominal memory capacity. The first seed
contains Snapdragon 8 Elite, 8 Gen 2 and 865 families. Additions must be
fact-checked; never silently infer a variant from its GPU model alone.

`handheld_profiles.cpp` compares reported machine and physical event-device names
with aliases, selecting the longest unambiguous family match. It uses RAM as a
*secondary* signal for an unambiguous SKU. If identification fails, no preset
is applied. Existing configurations are never overwritten at feature upgrade.

User-written presets are saved as:
`~/.config/lichii/handheld-presets/<family>-<model>.json`

Only allowlisted global performance settings are saved. They deliberately
exclude ROM directories, game saves, keys, Steam data, passwords, and button maps.

On a genuinely new Lichii global config, or on the NEXT launch after using
Reset to Defaults, an exact-model user preset is loaded at most once. If no
preset exists, stock Lichii settings remain intact. Manual Reset to Defaults
restores stock settings immediately and blocks automatic changes for the rest
of that same process. The next launch is eligible for a saved preset.

## Controller identity

SDL3 provides the same controller list that Lichii's mapping engine uses.
Its extended device package now includes the Linux device path, vendor,
product and SDL instance ID (without reading controller events or serials).
The routing layer also inspects physical device names in sysfs and the
configured ArmadaOS controller emulation mode in
`/etc/armada/controller.conf`.

On ArmadaOS, InputPlumber can transform one physical handheld into a virtual
Xbox 360 / Steam Deck / other target. Lichii must not mistake a generic
Xbox name for proof that a controller is built in. A virtual target can only
be inferred when it has a verifiable virtual device path, its label matches
the configured mode, and the physical handheld source is present. If more
than one target is plausible, or the path is not verifiable, automatic
assignment is paused. No udev permissions, services or controller modes
are modified by Lichii.

## Player assignments

With **Prefer external controller for Player 1 = ON** (default):
- Built-in only => P1 built-in
- Built-in + external => P1 first external; built-in unused
- Built-in + two externals => P1/P2 external 1/external 2
- Built-in disabled + externals => P1/P2 first/second external

With the preference **OFF**:
- Built-in + externals => P1 built-in, P2 first external
- Built-in disabled => P1/P2 first/second external

"First" means lowest SDL connection-instance ID among available controllers,
not alphabetic order. A physical source and its virtual target must never
occupy two player slots.

Automatic assignment runs on startup and probes hotplug state only when
no game is running, every 2.5 seconds. Changes are not applied during
gameplay. An existing manual mapping from before this feature is preserved;
subsequent manual changes pause automatic assignment until the user explicitly
re-enables it. The control to enable/disable automation is separate from
the control choosing external-first versus built-in-first.

The diagnostic view is under **Help > Hardware & Controller Diagnostics**,
with Rescan, Copy, automatic preference checkboxes, Apply Now, and
Save current settings as the detected handheld default. Errors or ambiguous
identity never interrupt game startup.

## Validation checklist (do not promote until complete)

- Native AArch64 build with the `lichii-debug` Toolbox.
- Confirm Odin 3 Ultra model and chipset and that a saved preset activates only
  on fresh install/after reset, never while resetting.
- Confirm stock settings immediately after Reset to Defaults.
- Confirm ArmadaOS `deck-uhid` and `xb360` virtual controller path and
  SDL gamepad visibility.
- Confirm built-in-only, external-only, built-in + 1 external and built-in + 2
  externals; include Steam Controller and Xbox One via Bluetooth/USB/dongle.
- Confirm mode switching with an active game causes no remapping until idle.
- Confirm existing manual mappings are preserved and manual changes pause auto.
- Confirm current Ocarina and Tears of the Kingdom launches, FPS, Steam menus,
  stable executable checksum and ROMs remain unaffected.

This design intentionally cannot guarantee a controller is "always available"
if the OS/SDL layer exposes no usable device. It diagnoses that state and
never hacks low-level permissions.
