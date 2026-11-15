// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <QJsonObject>
#include <QString>

namespace Core { class System; }
namespace InputCommon { class InputSubsystem; }

namespace ControllerRouting {
// Device classification is based on source path and virtual-device origin, never
// merely on the "Xbox" or "Steam" display name. No privileged access required.
bool PreferExternal();
bool AutomaticEnabled();
void SetPreferExternal(bool enabled);
void SetAutomaticEnabled(bool enabled);
void ResetToStock();
void AllowExplicitRemap();
QJsonObject Inspect(const InputCommon::InputSubsystem& input);
QString Format(const QJsonObject& inspection);
// Returns true only when a changed, validated mapping was applied to live settings.
// Hotplug updates are caller-gated to idle time; manual changes pause automation.
// Snapshot the final saved automatic assignment for manual-change protection.
void RecordAutomaticBaseline();
bool MaybeApply(const InputCommon::InputSubsystem& input, Core::System& system,
                QString* reason = nullptr);
} // namespace ControllerRouting
