// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <QJsonObject>
#include <QString>

namespace HandheldProfiles {
// The resource database is chipset -> handheld family -> manufacturer model.
// A match must be unambiguous before any preset may be applied.
QJsonObject Detect();
QString Format(const QJsonObject& detection);
// Only operates on genuinely new global configurations or after explicit Reset
// to Defaults and a full app restart. Never applies saved presets mid-reset.
bool MaybeApplyFirstLaunch(bool fresh_global_config, QString* reason = nullptr);
bool SaveCurrentAsDefault(QString* reason = nullptr);
void ResetToStock();
} // namespace HandheldProfiles
