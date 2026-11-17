# Odin 3 Ultra / ArmadaOS controller support

Odin-specific Lichii GUI builds include the native InputPlumber **deck-uhid**
bridge and the existing automatic Player 1 assignment system.

## How it works

- If the host config (`/etc/armada/controller.conf`, or
  `/run/host/etc/armada/controller.conf` inside toolbox) specifies
  `controller_type=deck-uhid`, the Linux SDL driver looks for exactly one
  **virtual**, sysfs-verified `28DE:12F0` HIDRAW device.
- The bridge converts the 64-byte Steam Deck HID report into a process-local
  SDL3 virtual gamepad. Buttons, sticks, triggers, and L4/L5/R4/R5 are mapped.
  It never changes InputPlumber mode or creates a system-wide input device.
- The verified HIDRAW sysfs origin is used by the existing controller router
  to distinguish the handheld from the external Steam Controller `28DE:1302`.
- For `deck-uhid` only, GUI startup defaults `SDL_HIDAPI_UDEV=0` *before*
  SDL initialization. This switches HIDAPI hotplug discovery to polling, which
  restored external Steam Controller plug/unplug handling in Fedora toolbox.
- Both mechanisms leave other Linux devices, other Armada controller modes,
  Windows, and macOS alone.

## Controls and overrides

The bridge automatically enables itself when `deck-uhid` is configured and a
unique virtual `28DE:12F0` is present. To disable it for one launch, set
`LICHII_ODIN_DECK_UHID_BRIDGE=0`.

A pre-existing `SDL_HIDAPI_UDEV` environment variable is honored; to switch
back to udev-based HIDAPI enumeration set `SDL_HIDAPI_UDEV=1`.

In Lichii, automatic Player 1 priority is managed by
`~/.config/lichii/controller-routing.ini` and the controller assignment UI.
The existing router intentionally avoids remapping while a game is running or
a modal settings dialog is open. Main-menu hotplug switching is supported;
in-game handoff is not yet promised.

## Validation (Odin 3 Ultra, Fedora 44 / InputPlumber 0.81.0)

- HID probe: 5,020 valid reports, no malformed reports.
- SDL3 virtual gamepad prototype: 5,387 valid reports, face buttons and rear
  L4/R4 validated; other rear buttons are mapped but not all separately tested.
- Integrated native controller experiment: ARM64 Lichii compiled successfully,
  onboard controls functioned, Steam Controller plug/unplug and return to the
  onboard Player 1 worked at the game list with `SDL_HIDAPI_UDEV=0`.
- Shader optimization code and per-game settings are unchanged by this feature.

The feature is guarded on Linux. A normal host without ArmadaOS `deck-uhid`
mode simply uses its existing SDL controller path.
