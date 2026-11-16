// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <vector>
#include <QJsonObject>
#include <QString>

namespace InputCommon { class InputSubsystem; }
namespace VkDeviceInfo { class Record; }

namespace HardwareDiagnostics {
// All probes are read-only. Missing data is explicitly reported as unavailable.
// No ROM filenames, input events, Steam account data, or serials are collected.
QJsonObject Collect(const std::vector<VkDeviceInfo::Record>& gpus,
                    const InputCommon::InputSubsystem& input);
QString FormatReport(const QJsonObject& report);
bool SaveReport(const QJsonObject& report);
QString ReportPath();
} // namespace HardwareDiagnostics
