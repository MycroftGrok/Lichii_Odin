# Linux/SteamOS-style operating systems for AYN Odin 3 and Odin 2

Research date: 2026-11-10. This note does **not** authorize flashing or changing bootloaders. Installing any OS can risk existing partitions/data; use the current device-specific documentation.

| OS | Odin 3 | Odin 2 family | What it offers | Recommendation |
|---|---|---|---|---|
| [ArmadaOS](https://github.com/armada-os/armada) | Already proven on the user's Odin 3 Ultra; official continued improvements through 2026-11-09 | Project supports multiple Odin 2 models; verify specific model | Fedora bootc, Steam-style Game Mode, Plasma desktop, FEX/Proton, handheld management and updates | **Keep for Lichii development** |
| [Holodor](https://github.com/transentient/holodor) | Public Odin 3 instructions and images advertised | Does not claim all Odin 2 models | Valve Holo Core ARM64 Steam userspace on a ROCKNIX-based kernel; Big Picture, Plasma/Arch-oriented approach | Viable alternative to test on separate media; author says Armada is more mature |
| [Kettle Linux](https://github.com/kettlelinux/kettlelinux) | Port booting in development; repository does not yet advertise public Odin 3 build | Odin 2 **Portal** supported; not evidence that every original Odin 2 variant is supported | SteamOS-like Valve ARM64 client, Game Mode, Plasma, A/B image updates | Watch closely; promising SteamOS-like architecture |
| [ROCKNIX](https://rocknix.org/devices/ayn/odin2portal/) | Check exact current device list | Odin 2 **Portal** has documented support | Mainline Linux, Freedreno/Turnip, Sway/EmulationStation | Excellent retro-emulation focus, not a full SteamOS desktop replacement |
| Bazzite | No official Odin 3 image verified in this research | No device-specific Odin 2 image verified | Well-known SteamOS-style Linux, but device-specific ARM64 boot support cannot be presumed | Do not flash generic Bazzite images to an Odin |

**Bottom line:** There is no demonstrated need to replace the already-working ArmadaOS installation to get Lichii acceleration. The bottleneck was Lichii selecting llvmpipe inside its toolbox. Restricting Vulkan to the Freedreno/Turnip ICD switched to hardware acceleration and the user observed 60 FPS in Ocarina of Time.

Source references:
- Armada: https://github.com/armada-os/armada/releases (2026-11-09 release notes)
- Holodor: https://github.com/transentient/holodor (Odin 3 download and install support; author explicitly describes Armada as more mature)
- Kettle: https://github.com/kettlelinux/kettlelinux and https://github.com/kettlelinux/kettlelinux/blob/main/docs/ODIN3.md (development stage and first tested images)
- ROCKNIX: https://rocknix.org/devices/ayn/odin2portal/
