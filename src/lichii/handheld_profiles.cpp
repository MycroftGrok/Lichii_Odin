// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "handheld_profiles.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <limits>
#include <vector>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSettings>
#include <QStringList>

#include "common/settings.h"

namespace {
bool suppress_profiles_after_reset = false;

QString ReadSmall(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 1024 * 1024)
        return {};
    QString content = QString::fromUtf8(file.readAll());
    content.replace(QChar::Null, QChar(u' '));
    return content.trimmed();
}

QJsonObject ReadJson(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 1024 * 1024)
        return {};
    QJsonParseError err;
    const auto doc = QJsonDocument::fromJson(file.readAll(), &err);
    return err.error == QJsonParseError::NoError && doc.isObject() ? doc.object() : QJsonObject{};
}

QSettings Preferences() {
    return QSettings(QDir::homePath() + QStringLiteral("/.config/lichii/handheld-profiles.ini"),
                     QSettings::IniFormat);
}

QString UserPresetFile(const QString& profile_id) {
    static const QRegularExpression safe(QStringLiteral(R"(^[a-z0-9-]+$)"));
    if (!safe.match(profile_id).hasMatch())
        return {};
    return QDir::homePath() + QStringLiteral("/.config/lichii/handheld-presets/") +
           profile_id + QStringLiteral(".json");
}

QStringList AllowedSettingNames() {
    // Never collect Steam credentials, user data, paths, keys, save-game state or
    // controller button maps. These are explicit emulator performance settings.
    return {QStringLiteral("use_multi_core"),
            QStringLiteral("use_speed_limit"),
            QStringLiteral("fps_limit"),
            QStringLiteral("backend"),
            QStringLiteral("vulkan_device"),
            QStringLiteral("resolution_setup"),
            QStringLiteral("scaling_filter"),
            QStringLiteral("gpu_accuracy"),
            QStringLiteral("nvdec_emulation"),
            QStringLiteral("use_asynchronous_gpu_emulation"),
            QStringLiteral("use_asynchronous_shaders"),
            QStringLiteral("async_presentation"),
            QStringLiteral("use_disk_shader_cache"),
            QStringLiteral("use_vulkan_driver_pipeline_cache")};
}

double RamGigabytes() {
#ifdef Q_OS_LINUX
    static const QRegularExpression re(QStringLiteral(R"((?m)^MemTotal:\s*(\d+)\s+kB)"));
    const auto match = re.match(ReadSmall(QStringLiteral("/proc/meminfo")));
    if (match.hasMatch()) {
        bool ok = false;
        const auto kib = match.captured(1).toDouble(&ok);
        if (ok)
            return kib / 1024.0 / 1024.0;
    }
#endif
    return 0.0;
}

QJsonObject FindModel() {
    const auto catalog = ReadJson(QStringLiteral(":/handheld/catalog.json"));
    if (catalog.value(QStringLiteral("schema_version")).toInt() != 1)
        return QJsonObject{{QStringLiteral("status"), QStringLiteral("catalog-unavailable")}};

    QString machine;
#ifdef Q_OS_LINUX
    machine = ReadSmall(QStringLiteral("/sys/devices/soc0/machine"));
    if (machine.isEmpty())
        machine = ReadSmall(QStringLiteral("/proc/device-tree/model"));
#endif
    QString probe = machine;
#ifdef Q_OS_LINUX
    const QDir input(QStringLiteral("/sys/class/input"));
    for (const QString& name : input.entryList(QStringList{QStringLiteral("event*")},
                                               QDir::AllDirs | QDir::System | QDir::NoDotAndDotDot)) {
        probe += QChar(u'\n') + ReadSmall(input.filePath(name + QStringLiteral("/device/name")));
    }
#endif
    const double ram = RamGigabytes();
    QJsonObject best_device, best_chipset;
    int best_match_length = 0;
    bool tied = false;
    for (const auto& chipset_value : catalog.value(QStringLiteral("chipsets")).toArray()) {
        const auto chipset = chipset_value.toObject();
        for (const auto& handheld_value : chipset.value(QStringLiteral("handhelds")).toArray()) {
            const auto handheld = handheld_value.toObject();
            int local_best = 0;
            for (const auto& alias_value : handheld.value(QStringLiteral("aliases")).toArray()) {
                const QString alias = alias_value.toString();
                if (alias.size() >= 6 && probe.contains(alias, Qt::CaseInsensitive))
                    local_best = std::max(local_best, static_cast<int>(alias.size()));
            }
            if (local_best > best_match_length) {
                best_device = handheld;
                best_chipset = chipset;
                best_match_length = local_best;
                tied = false;
            } else if (local_best > 0 && local_best == best_match_length &&
                       handheld.value(QStringLiteral("id")).toString() !=
                           best_device.value(QStringLiteral("id")).toString()) {
                tied = true;
            }
        }
    }
    if (best_match_length == 0 || tied)
        return QJsonObject{{QStringLiteral("status"),
                             tied ? QStringLiteral("ambiguous-family")
                                  : QStringLiteral("unknown-handheld")},
                           {QStringLiteral("probe_source"), machine}};

    // The same Odin 2 input name can be reused by Portal/Mini. Without a
    // family-specific machine identifier we refuse to assume ordinary Odin 2.
    if (best_device.value(QStringLiteral("id")).toString() ==
            QStringLiteral("ayn-odin-2") &&
        !machine.contains(QStringLiteral("Odin 2"), Qt::CaseInsensitive) &&
        !machine.contains(QStringLiteral("Odin2"), Qt::CaseInsensitive)) {
        return QJsonObject{{QStringLiteral("status"), QStringLiteral("ambiguous-odin2-family")},
                           {QStringLiteral("probe_source"), machine}};
    }

    QJsonObject selected_model;
    double closest = std::numeric_limits<double>::max();
    bool equally_close = false;
    for (const auto& model_value : best_device.value(QStringLiteral("models")).toArray()) {
        const auto model = model_value.toObject();
        const double diff = std::abs(model.value(QStringLiteral("ram_gib")).toDouble() - ram);
        if (diff + 0.05 < closest) {
            selected_model = model;
            closest = diff;
            equally_close = false;
        } else if (std::abs(diff - closest) <= 0.05) {
            equally_close = true;
        }
    }
    const bool variant_verified = ram > 0.0 && closest < 2.0 && !equally_close &&
                                  !selected_model.isEmpty();
    const QString family = best_device.value(QStringLiteral("id")).toString();
    const QString profile = variant_verified
        ? family + QStringLiteral("-") + selected_model.value(QStringLiteral("id")).toString()
        : QString{};
    const QString path = UserPresetFile(profile);
    return QJsonObject{
        {QStringLiteral("status"), variant_verified
             ? QStringLiteral("exact-variant") : QStringLiteral("family-only")},
        {QStringLiteral("manufacturer"), best_device.value(QStringLiteral("manufacturer")).toString()},
        {QStringLiteral("chipset"), best_chipset.value(QStringLiteral("name")).toString()},
        {QStringLiteral("handheld"), best_device.value(QStringLiteral("handheld")).toString()},
        {QStringLiteral("model"), variant_verified
             ? selected_model.value(QStringLiteral("name")).toString() : QStringLiteral("Uncertain")},
        {QStringLiteral("profile_id"), profile},
        {QStringLiteral("ram_observed_gib"), ram},
        {QStringLiteral("user_preset_exists"), !path.isEmpty() && QFileInfo::exists(path)},
        {QStringLiteral("probe_source"), machine}};
}

} // namespace

namespace HandheldProfiles {
QJsonObject Detect() {
    auto match = FindModel();
    QSettings prefs = Preferences();
    match[QStringLiteral("last_applied_profile")] =
        prefs.value(QStringLiteral("last_applied_profile")).toString();
    match[QStringLiteral("stock_reset_pending")] =
        prefs.value(QStringLiteral("pending_after_reset"), false).toBool();
    return match;
}

QString Format(const QJsonObject& info) {
    QStringList lines{QStringLiteral("HANDHELD PROFILE DATABASE"),
        QStringLiteral("Detection: ") + info.value(QStringLiteral("status")).toString()};
    if (!info.value(QStringLiteral("profile_id")).toString().isEmpty()) {
        lines << QStringLiteral("Chipset: ") + info.value(QStringLiteral("chipset")).toString()
              << QStringLiteral("Device: ") +
                 info.value(QStringLiteral("manufacturer")).toString() + QChar(u' ') +
                 info.value(QStringLiteral("handheld")).toString()
              << QStringLiteral("Model: ") + info.value(QStringLiteral("model")).toString()
              << QStringLiteral("Profile ID: ") +
                 info.value(QStringLiteral("profile_id")).toString()
              << QStringLiteral("Saved user preset: ") +
                 (info.value(QStringLiteral("user_preset_exists")).toBool()
                     ? QStringLiteral("Yes") : QStringLiteral("No (stock Lichii defaults retained)"));
    } else {
        lines << QStringLiteral("No exact device preset selected; no settings will be overwritten.");
    }
    lines << QStringLiteral("Last applied profile: ") +
                 info.value(QStringLiteral("last_applied_profile")).toString();
    return lines.join(QChar(u'\n'));
}

bool MaybeApplyFirstLaunch(bool fresh_global_config, QString* reason) {
    auto say = [reason](const QString& message) {
        if (reason) *reason = message;
    };
    if (suppress_profiles_after_reset) {
        say(QStringLiteral("Stock reset active; deferred until restart"));
        return false;
    }
    QSettings prefs = Preferences();
    const bool after_reset = prefs.value(QStringLiteral("pending_after_reset"), false).toBool();
    if (!fresh_global_config && !after_reset) {
        say(QStringLiteral("Existing settings preserved"));
        return false;
    }
    const auto detected = FindModel();
    if (detected.value(QStringLiteral("status")).toString() != QStringLiteral("exact-variant")) {
        say(QStringLiteral("Handheld model not unambiguously identified; stock settings preserved"));
        return false;
    }
    const QString id = detected.value(QStringLiteral("profile_id")).toString();
    const QString preset = UserPresetFile(id);
    if (preset.isEmpty()) {
        say(QStringLiteral("Invalid profile ID; stock settings preserved"));
        return false;
    }
    if (prefs.value(QStringLiteral("last_applied_profile")).toString() == id &&
        !after_reset) {
        say(QStringLiteral("Profile was already processed"));
        return false;
    }
    if (!QFileInfo::exists(preset)) {
        prefs.setValue(QStringLiteral("last_applied_profile"), id);
        prefs.remove(QStringLiteral("pending_after_reset"));
        say(QStringLiteral("Device detected; no user preset. Using Lichii stock defaults."));
        return false;
    }
    const auto json = ReadJson(preset);
    if (json.value(QStringLiteral("schema_version")).toInt() != 1 ||
        json.value(QStringLiteral("profile_id")).toString() != id ||
        !json.value(QStringLiteral("settings")).isObject()) {
        say(QStringLiteral("Preset format invalid; stock defaults retained"));
        return false;
    }

    const auto settings = json.value(QStringLiteral("settings")).toObject();
    const QStringList allow = AllowedSettingNames();
    // Strict validation before mutating any setting.
    static const QRegularExpression safe_value(
        QStringLiteral(R"(^(true|false|-?[0-9]+)$)"));
    for (auto it = settings.constBegin(); it != settings.constEnd(); ++it) {
        if (!allow.contains(it.key()) || !it.value().isString() ||
            !safe_value.match(it.value().toString()).hasMatch() ||
            Settings::values.linkage.by_key.find(it.key().toStdString()) ==
                Settings::values.linkage.by_key.end()) {
            say(QStringLiteral("Preset contains unknown or invalid settings; nothing applied"));
            return false;
        }
    }

    int changed = 0;
    for (auto it = settings.constBegin(); it != settings.constEnd(); ++it) {
        auto* setting = Settings::values.linkage.by_key.at(it.key().toStdString());
        const std::string wanted = it.value().toString().toStdString();
        if (setting->ToStringGlobal() != wanted) {
            setting->LoadString(wanted);
            ++changed;
        }
    }
    prefs.setValue(QStringLiteral("last_applied_profile"), id);
    prefs.remove(QStringLiteral("pending_after_reset"));
    say(QStringLiteral("Applied %1 saved performance settings from %2").arg(changed).arg(id));
    return changed > 0;
}

bool SaveCurrentAsDefault(QString* reason) {
    auto say = [reason](const QString& message) {
        if (reason) *reason = message;
    };
    const auto detected = FindModel();
    if (detected.value(QStringLiteral("status")).toString() != QStringLiteral("exact-variant")) {
        say(QStringLiteral("Cannot save: exact handheld model/variant not confidently identified"));
        return false;
    }
    const QString id = detected.value(QStringLiteral("profile_id")).toString();
    const QString path = UserPresetFile(id);
    if (path.isEmpty()) {
        say(QStringLiteral("Unsafe profile ID"));
        return false;
    }
    const QString directory = QFileInfo(path).absolutePath();
    if (QFileInfo(directory).isSymLink() || QFileInfo(path).isSymLink() ||
        !QDir().mkpath(directory)) {
        say(QStringLiteral("Preset directory could not be safely created"));
        return false;
    }
    QJsonObject values;
    for (const QString& key : AllowedSettingNames()) {
        auto it = Settings::values.linkage.by_key.find(key.toStdString());
        if (it != Settings::values.linkage.by_key.end()) {
            const QString value = QString::fromStdString(it->second->ToStringGlobal());
            values.insert(key, value);
        }
    }
    const QJsonObject document{
        {QStringLiteral("schema_version"), 1},
        {QStringLiteral("profile_id"), id},
        {QStringLiteral("chipset"), detected.value(QStringLiteral("chipset")).toString()},
        {QStringLiteral("device"), detected.value(QStringLiteral("handheld")).toString()},
        {QStringLiteral("model"), detected.value(QStringLiteral("model")).toString()},
        {QStringLiteral("settings"), values}};
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly)) {
        say(QStringLiteral("Unable to write handheld preset"));
        return false;
    }
    const QByteArray payload = QJsonDocument(document).toJson(QJsonDocument::Indented);
    if (output.write(payload) != payload.size() || !output.commit()) {
        say(QStringLiteral("Preset save failed"));
        return false;
    }
    QFile::setPermissions(path, QFile::ReadOwner | QFile::WriteOwner);
    say(QStringLiteral("Saved %1 allowed settings to %2. Preset activates on first setup after reset.")
            .arg(values.size()).arg(path));
    return true;
}

void ResetToStock() {
    suppress_profiles_after_reset = true;
    QSettings prefs = Preferences();
    prefs.remove(QStringLiteral("last_applied_profile"));
    prefs.setValue(QStringLiteral("pending_after_reset"), true);
    prefs.sync();
}
} // namespace HandheldProfiles
