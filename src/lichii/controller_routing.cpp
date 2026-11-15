// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "controller_routing.h"

#include <algorithm>
#include <string>
#include <limits>
#include <vector>

#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QRegularExpression>
#include <QSettings>
#include <QStringList>

#include <SDL3/SDL_hidapi.h>

#include "common/param_package.h"
#include "common/settings.h"
#include "core/core.h"
#include "hid_core/hid_core.h"
#include "input_common/main.h"

namespace {

// Suppresses reconfiguration for the remainder of this process after a user
// selects Lichii stock defaults. The next launch is allowed to use detection.
bool suppress_auto_after_stock_reset = false;

struct Candidate {
    Common::ParamPackage device;
    QString name;
    QString path;
    QString sysfs_path;
    QString transport;
    int order = std::numeric_limits<int>::max();
    bool virtual_node = false;
    bool built_in = false;
    QString identity_reason;
};

struct ScanResult {
    std::vector<Candidate> devices;
    bool physical_builtin_present = false;
    bool ambiguous_virtual_builtin = false;
    QString armada_mode;
    QString detected_model;
    QString note;
};

QString ReadSmall(const QString& path) {
    QFile input(path);
    if (!input.open(QIODevice::ReadOnly) || input.size() > 16384)
        return {};
    QString text = QString::fromUtf8(input.readAll());
    text.replace(QChar::Null, QChar(u' '));
    return text.trimmed();
}

bool IsBuiltInSourceName(const QString& name) {
    static const QRegularExpression native(
        QStringLiteral(R"(\b(ayn[ -]?)?(odin\s*[23]|odin3|retroid|pocket\s*[456]|thor)\b.*\b(gamepad|controller|pad)\b|\b(ayn|retroid).*\b(gamepad|controller)\b)"),
        QRegularExpression::CaseInsensitiveOption);
    return native.match(name).hasMatch();
}

QString ConfigPath() {
    return QDir::homePath() + QStringLiteral("/.config/lichii/controller-routing.ini");
}
QSettings Preferences() {
    return QSettings(ConfigPath(), QSettings::IniFormat);
}

// Read-only USB presence check shared between diagnostics and the router.
// HID presence does not mean SDL can actually map the controller.
QStringList SteamUsbHidNodes() {
    QStringList nodes;
#ifdef Q_OS_LINUX
    const QDir hidraw(QStringLiteral("/sys/class/hidraw"));
    for (const auto& entry : hidraw.entryList(
             QStringList{QStringLiteral("hidraw*")},
             QDir::AllDirs | QDir::System | QDir::NoDotAndDotDot)) {
        const QString sysfs = QFileInfo(
            hidraw.filePath(entry + QStringLiteral("/device"))).canonicalFilePath();
        if (sysfs.contains(QStringLiteral("28DE:1302"), Qt::CaseInsensitive)) {
            const QString node = QStringLiteral("/dev/") + entry;
            nodes << node;
        }
    }
#endif
    return nodes;
}

QString ArmadaMode() {
#ifdef Q_OS_LINUX
    const QRegularExpression mode(QStringLiteral(R"((?m)^controller_type=([^\r\n]+))"));
    // Toolbox exposes the host /etc at /run/host/etc, while its own /etc
    // is a container image. Never assume a missing local file means
    // ArmadaOS controller emulation is disabled.
    for (const auto& path : {QStringLiteral("/run/host/etc/armada/controller.conf"),
                             QStringLiteral("/etc/armada/controller.conf")}) {
        const auto match = mode.match(ReadSmall(path));
        if (match.hasMatch())
            return match.captured(1).trimmed();
    }
    return {};
#else
    return {};
#endif
}

QString DeviceSysfs(const QString& devnode) {
#ifdef Q_OS_LINUX
    const QRegularExpression event(QStringLiteral(R"(^/dev/input/(event[0-9]+)$)"));
    const auto match = event.match(devnode);
    if (match.hasMatch())
        return QFileInfo(QStringLiteral("/sys/class/input/") +
                         match.captured(1) + QStringLiteral("/device")).canonicalFilePath();
    // InputPlumber deck-uhid is HID-only: it has a /dev/hidrawN node and NO
    // /dev/input/eventN gamepad. Preserve its virtual origin for built-in P1
    // classification, rather than incorrectly considering it an external pad.
    const QRegularExpression hidraw(QStringLiteral(R"(^/dev/(hidraw[0-9]+)$)"));
    const auto raw_match = hidraw.match(devnode);
    if (raw_match.hasMatch())
        return QFileInfo(QStringLiteral("/sys/class/hidraw/") +
                         raw_match.captured(1) + QStringLiteral("/device")).canonicalFilePath();
    return {};
#else
    return {};
#endif
}

QString DeviceTransport(const QString& path, const QString& sysfs) {
    const QString canonical = sysfs.toLower();
    if (canonical.contains(QStringLiteral("/virtual/")) ||
        canonical.contains(QStringLiteral("/uhid/")))
        return QStringLiteral("Virtual (transport hidden)");
    if (canonical.contains(QStringLiteral("/bluetooth/")))
        return QStringLiteral("Bluetooth");
    if (canonical.contains(QStringLiteral("/usb")))
        return QStringLiteral("USB or USB wireless dongle");
    if (!path.isEmpty())
        return QStringLiteral("Connected (transport unknown)");
    return QStringLiteral("Unknown");
}

bool IsVirtualBuiltInModeName(const QString& mode, const QString& name) {
    const auto matches = [&name](const QString& expression) {
        return name.contains(QRegularExpression(
            expression, QRegularExpression::CaseInsensitiveOption));
    };
    if (mode == QStringLiteral("xb360"))
        return matches(QStringLiteral(R"(x[ -]?box\s*360)"));
    if (mode == QStringLiteral("xbox-elite"))
        return matches(QStringLiteral(R"(x[ -]?box.*elite)"));
    if (mode == QStringLiteral("xbox-series"))
        return matches(QStringLiteral(R"(x[ -]?box.*(series|one))"));
    if (mode == QStringLiteral("deck") || mode == QStringLiteral("deck-uhid") ||
        mode == QStringLiteral("hori-steam"))
        return matches(QStringLiteral(R"(steam\s*(deck|controller))"));
    if (mode == QStringLiteral("ds5") || mode == QStringLiteral("ds5-edge"))
        return matches(QStringLiteral(R"(dualsense|wireless controller)"));
    // Generic input mode has no distinctive target label: never infer identity
    // from its name alone.
    return false;
}

ScanResult Scan(const InputCommon::InputSubsystem& subsystem) {
    ScanResult result;
    result.armada_mode = ArmadaMode();
#ifdef Q_OS_LINUX
    result.detected_model = ReadSmall(QStringLiteral("/sys/devices/soc0/machine"));
    if (result.detected_model.isEmpty())
        result.detected_model = ReadSmall(QStringLiteral("/proc/device-tree/model"));
    const QDir sys(QStringLiteral("/sys/class/input"));
    for (const QString& entry : sys.entryList(QStringList{QStringLiteral("event*")},
                                              QDir::AllDirs | QDir::System | QDir::NoDotAndDotDot)) {
        const QString name = ReadSmall(sys.filePath(entry + QStringLiteral("/device/name")));
        if (IsBuiltInSourceName(name)) {
            result.physical_builtin_present = true;
            break;
        }
    }
#endif
    // InputSubsystem is the source of truth for controllers Lichii can actually map.
    // Ignore virtual keyboard/mouse and duplicated backends.
    for (const auto& device : subsystem.GetInputDevices()) {
        const std::string engine = device.Get("engine", "");
        if (engine != "sdl" && engine != "joycon" && engine != "gcpad")
            continue;
        Candidate item;
        item.device = device;
        item.name = QString::fromStdString(device.Get("display", "Unknown"));
        item.path = QString::fromStdString(device.Get("path", ""));
        item.sysfs_path = DeviceSysfs(item.path);
        item.virtual_node = item.sysfs_path.contains(QStringLiteral("/virtual/")) ||
                            item.sysfs_path.contains(QStringLiteral("/uhid/"));
        item.transport = DeviceTransport(item.path, item.sysfs_path);
        try {
            item.order = std::stoi(device.Get("instance_id", ""));
        } catch (...) {
            // Joy-Con and non-SDL backends may have no SDL connection-order ID.
        }
        const QString sysname = item.path.startsWith(QStringLiteral("/dev/input/event"))
            ? ReadSmall(QStringLiteral("/sys/class/input/") +
                        QFileInfo(item.path).fileName() + QStringLiteral("/device/name"))
            : QString{};
        if (IsBuiltInSourceName(sysname) || IsBuiltInSourceName(item.name)) {
            item.built_in = true;
            item.identity_reason = QStringLiteral("Physical handheld controller identity");
        }
        result.devices.push_back(std::move(item));
    }

    // SDL gamepad display names can be generic, e.g. "Xbox 360 Controller" for
    // both an external Xbox pad and InputPlumber's virtual target. Only correlate
    // the ArmadaOS target when its device is explicitly virtual, a matching
    // physical handheld source exists, and precisely one possible target exists.
    int virtual_index = -1;
    int virtual_matches = 0;
    for (std::size_t i = 0; i < result.devices.size(); ++i) {
        const auto& item = result.devices[i];
        if (item.built_in || !item.virtual_node ||
            !IsVirtualBuiltInModeName(result.armada_mode, item.name))
            continue;
        ++virtual_matches;
        virtual_index = static_cast<int>(i);
    }
    if (result.physical_builtin_present && virtual_matches == 1) {
        auto& item = result.devices[static_cast<std::size_t>(virtual_index)];
        item.built_in = true;
        item.identity_reason = QStringLiteral("Sole matching virtual InputPlumber mode candidate");
    } else if (result.physical_builtin_present && virtual_matches > 1) {
        result.ambiguous_virtual_builtin = true;
        result.note = QStringLiteral(
            "Multiple virtual controllers match the built-in mode. Automatic remapping paused "
            "rather than treating an external Xbox/Steam controller as internal.");
    }
    // A generic mode-like display name with no traceable virtual sysfs path
    // cannot safely be labeled internal or external. Do not guess.
    if (result.physical_builtin_present && virtual_matches == 0 &&
        std::none_of(result.devices.begin(), result.devices.end(),
                     [](const Candidate& d) { return d.built_in; })) {
        for (const auto& item : result.devices) {
            if (IsVirtualBuiltInModeName(result.armada_mode, item.name)) {
                result.ambiguous_virtual_builtin = true;
                result.note = QStringLiteral(
                    "A controller matches ArmadaOS's configured virtual mode but its sysfs "
                    "origin is not verifiable. Automatic mapping paused.");
                break;
            }
        }
    }

    std::stable_sort(result.devices.begin(), result.devices.end(),
                     [](const Candidate& a, const Candidate& b) {
                         return a.order < b.order;
                     });
    if (result.physical_builtin_present &&
        std::none_of(result.devices.begin(), result.devices.end(),
                     [](const Candidate& d) { return d.built_in; }) &&
        result.note.isEmpty()) {
        result.note = QStringLiteral(
            "Physical handheld source exists but no matching gamepad is visible to SDL. "
            "InputPlumber may not be exposing a target to Lichii.");
    }
    return result;
}

QString ActualPlayerDevice(std::size_t index, const ScanResult& scan) {
    const auto& players = Settings::values.players.GetValue(true);
    if (index >= players.size() || !players[index].connected)
        return QStringLiteral("Disconnected");
    for (const auto& value : players[index].buttons) {
        const Common::ParamPackage button(value);
        const std::string engine = button.Get("engine", "");
        if (engine != "sdl" && engine != "joycon" && engine != "gcpad")
            continue;
        const std::string guid = button.Get("guid", "");
        const int port = button.Get("port", 0);
        for (const auto& item : scan.devices) {
            if (item.device.Get("engine", "") == engine &&
                item.device.Get("guid", "") == guid &&
                item.device.Get("port", 0) == port)
                return item.name;
        }
        return QStringLiteral("Unresolved: controller not detected by SDL");
    }
    return QStringLiteral("No single SDL controller mapped");
}

QString PlayerHash(std::size_t index) {
    const auto& players = Settings::values.players.GetValue(true);
    if (index >= players.size())
        return {};
    const auto& p = players[index];

    // Disconnected Player 2 has no active controller mapping.
    // Ignore inactive bindings that configuration loading may normalize.
    // Connected controllers retain full manual-binding protection.
    if (index == 1 && !p.connected)
        return QStringLiteral("disconnected");

    QByteArray data;
    data.append(p.connected ? '1' : '0');
    data.append(QByteArray::number(static_cast<int>(p.controller_type)));
    for (const auto& binding : p.buttons) {
        data.append('\0');
        data.append(QByteArray::fromStdString(binding));
    }
    for (const auto& binding : p.analogs) {
        data.append('\0');
        data.append(QByteArray::fromStdString(binding));
    }
    for (const auto& binding : p.motions) {
        data.append('\0');
        data.append(QByteArray::fromStdString(binding));
    }
    return QString::fromLatin1(
        QCryptographicHash::hash(data, QCryptographicHash::Sha256).toHex());
}

bool ExistingControllerMappings() {
    const auto& players = Settings::values.players.GetValue(true);
    for (std::size_t p = 0; p < std::min<std::size_t>(2, players.size()); ++p) {
        for (const auto& button : players[p].buttons) {
            const Common::ParamPackage parsed(button);
            const auto engine = parsed.Get("engine", "");
            if (!engine.empty() && engine != "keyboard" && engine != "mouse")
                return true;
        }
    }
    return false;
}

QString Signature(const ScanResult& result, bool prefer_external) {
    QByteArray payload(prefer_external ? "external" : "internal");
    for (const auto& d : result.devices) {
        payload.append('\n');
        payload.append(QByteArray::fromStdString(d.device.Get("engine", "")));
        payload.append(':');
        payload.append(QByteArray::fromStdString(d.device.Get("guid", "")));
        payload.append(':');
        payload.append(QByteArray::fromStdString(d.device.Get("port", "")));
        payload.append(':');
        payload.append(d.built_in ? 'I' : 'E');
    }
    return QString::fromLatin1(
        QCryptographicHash::hash(payload, QCryptographicHash::Sha256).toHex());
}

void MapPlayer(std::size_t index, const Candidate* candidate,
               const InputCommon::InputSubsystem& input) {
    auto& players = Settings::values.players.GetValue(true);
    auto& p = players[index];
    if (!candidate) {
        p.connected = false;
        for (auto& button : p.buttons) button.clear();
        for (auto& analog : p.analogs) analog.clear();
        for (auto& motion : p.motions) motion.clear();
        return;
    }
    p.connected = true;
    p.controller_type = Settings::ControllerType::ProController;
    for (auto& button : p.buttons) button.clear();
    for (auto& analog : p.analogs) analog.clear();
    for (auto& motion : p.motions) motion.clear();
    for (const auto& [key, value] : input.GetButtonMappingForDevice(candidate->device)) {
        const auto n = static_cast<std::size_t>(key);
        if (n < p.buttons.size()) p.buttons[n] = value.Serialize();
    }
    for (const auto& [key, value] : input.GetAnalogMappingForDevice(candidate->device)) {
        const auto n = static_cast<std::size_t>(key);
        if (n < p.analogs.size()) p.analogs[n] = value.Serialize();
    }
    for (const auto& [key, value] : input.GetMotionMappingForDevice(candidate->device)) {
        const auto n = static_cast<std::size_t>(key);
        if (n < p.motions.size()) p.motions[n] = value.Serialize();
    }
}
} // namespace

namespace ControllerRouting {
bool PreferExternal() {
    QSettings prefs = Preferences();
    return prefs.value(QStringLiteral("prefer_external_player_1"), true).toBool();
}

bool AutomaticEnabled() {
    QSettings prefs = Preferences();
    return prefs.value(QStringLiteral("automatic_player_assignment"), true).toBool();
}

void SetPreferExternal(bool enabled) {
    QSettings prefs = Preferences();
    prefs.setValue(QStringLiteral("prefer_external_player_1"), enabled);
    // Changing this checkbox is an explicit choice to use automatic routing.
    // The next idle check can replace P1/P2 once; subsequent changes remain
    // protected by the saved mapping hashes unless the user opts in again.
    prefs.setValue(QStringLiteral("automatic_player_assignment"), true);
    prefs.setValue(QStringLiteral("explicit_takeover"), true);
    prefs.remove(QStringLiteral("last_signature"));
}

void SetAutomaticEnabled(bool enabled) {
    QSettings prefs = Preferences();
    prefs.setValue(QStringLiteral("automatic_player_assignment"), enabled);
    if (enabled)
        prefs.remove(QStringLiteral("last_signature"));
}

void AllowExplicitRemap() {
    QSettings prefs = Preferences();
    prefs.setValue(QStringLiteral("explicit_takeover"), true);
    prefs.remove(QStringLiteral("last_signature"));
}

void ResetToStock() {
    suppress_auto_after_stock_reset = true;
    // The upstream reset handler reinstates the original Lichii settings.
    // Remove only routing metadata; do not run auto-routing during reset.
    QSettings prefs = Preferences();
    prefs.clear();
    prefs.setValue(QStringLiteral("automatic_player_assignment"), true);
    prefs.setValue(QStringLiteral("reset_stock_pending_next_launch"), true);
    prefs.sync();
}

QJsonObject Inspect(const InputCommon::InputSubsystem& input) {
    const ScanResult scan = Scan(input);
    QJsonObject out;
    out[QStringLiteral("armada_controller_mode")] = scan.armada_mode;
    out[QStringLiteral("detected_handheld_model")] = scan.detected_model;
    out[QStringLiteral("physical_builtin_source_seen")] = scan.physical_builtin_present;
    out[QStringLiteral("ambiguous_identity")] = scan.ambiguous_virtual_builtin;
    out[QStringLiteral("prefer_external_player_1")] = PreferExternal();
    out[QStringLiteral("automatic_assignment_enabled")] = AutomaticEnabled();
    QSettings prefs = Preferences();
    out[QStringLiteral("last_routing_result")] =
        prefs.value(QStringLiteral("last_routing_result")).toString();
    QJsonArray steam_usb_nodes;
    for (const QString& node : SteamUsbHidNodes())
        steam_usb_nodes.append(node);
    out[QStringLiteral("steam_usb_hid_nodes")] = steam_usb_nodes;
    // SDL's HIDAPI enumeration is distinct from the joystick/gamepad API.
    // Do not open the device; only ask if it is enumerable in this container.
    bool steam_hid_enumerated = false;
#ifdef Q_OS_LINUX
    SDL_hid_device_info* info = SDL_hid_enumerate(0x28de, 0x1302);
    for (const SDL_hid_device_info* dev = info; dev; dev = dev->next) {
        if (dev->vendor_id == 0x28de && dev->product_id == 0x1302) {
            steam_hid_enumerated = true;
            break;
        }
    }
    SDL_hid_free_enumeration(info);
#endif
    out[QStringLiteral("steam_sdl_hid_enumerated")] = steam_hid_enumerated;
    out[QStringLiteral("actual_player_1")] = ActualPlayerDevice(0, scan);
    out[QStringLiteral("actual_player_2")] = ActualPlayerDevice(1, scan);
    out[QStringLiteral("note")] = scan.note;
    QJsonArray all;
    int external_count = 0;
    int internal_count = 0;
    for (const auto& item : scan.devices) {
        if (item.built_in) ++internal_count; else ++external_count;
        all.append(QJsonObject{
            {QStringLiteral("name"), item.name},
            {QStringLiteral("transport"), item.transport},
            {QStringLiteral("is_built_in"), item.built_in},
            {QStringLiteral("source_path"), item.path},
            {QStringLiteral("identity_reason"), item.identity_reason}});
    }
    out[QStringLiteral("devices")] = all;
    out[QStringLiteral("external_count")] = external_count;
    out[QStringLiteral("built_in_count")] = internal_count;
    return out;
}

QString Format(const QJsonObject& report) {
    QStringList lines{
        QStringLiteral("CONTROLLER DETECTION & ASSIGNMENT"),
        QStringLiteral("Handheld: ") + report.value(QStringLiteral("detected_handheld_model")).toString(),
        QStringLiteral("ArmadaOS mode: ") +
            report.value(QStringLiteral("armada_controller_mode")).toString(),
        QStringLiteral("Prefer external for P1: ") +
            (report.value(QStringLiteral("prefer_external_player_1")).toBool() ?
                 QStringLiteral("ON") : QStringLiteral("OFF")),
        QStringLiteral("Automatic mapping: ") +
            (report.value(QStringLiteral("automatic_assignment_enabled")).toBool() ?
                 QStringLiteral("ON") : QStringLiteral("OFF"))};
    const QString last_result = report.value(QStringLiteral("last_routing_result")).toString();
    if (!last_result.isEmpty()) {
        lines << QStringLiteral("Last routing check: ") + last_result;
    }
    const QJsonArray steam_hid =
        report.value(QStringLiteral("steam_usb_hid_nodes")).toArray();
    QStringList steam_paths;
    for (const auto& val : steam_hid)
        steam_paths << val.toString();
    lines << QStringLiteral("USB Steam Controller HID 28DE:1302: ") +
                 (steam_paths.isEmpty() ? QStringLiteral("NOT PRESENT")
                                        : steam_paths.join(QStringLiteral(", ")));
    lines << QStringLiteral("SDL HIDAPI enumerates Steam USB: ") +
                 (report.value(QStringLiteral("steam_sdl_hid_enumerated")).toBool()
                      ? QStringLiteral("YES") : QStringLiteral("NO"));
    lines << QStringLiteral("ACTUAL mapped Player 1: ") +
                 report.value(QStringLiteral("actual_player_1")).toString();
    lines << QStringLiteral("ACTUAL mapped Player 2: ") +
                 report.value(QStringLiteral("actual_player_2")).toString();
    const QJsonArray devices = report.value(QStringLiteral("devices")).toArray();
    bool steam_sdl = false;
    for (const auto& val : devices) {
        const auto item = val.toObject();
        if (!item.value(QStringLiteral("is_built_in")).toBool() &&
            item.value(QStringLiteral("name")).toString().contains(
                QStringLiteral("Steam Controller"), Qt::CaseInsensitive)) {
            steam_sdl = true;
            break;
        }
    }
    if (!steam_paths.isEmpty() && !steam_sdl) {
        lines << QStringLiteral(
            "WARNING: USB Steam Controller HID is present but SDL does not expose it; routing cannot assign this controller.");
    }
    if (devices.isEmpty()) lines << QStringLiteral("No gamepads exposed to Lichii.");
    const bool has_external = report.value(QStringLiteral("external_count")).toInt() > 0;
    const bool prefer_external =
        report.value(QStringLiteral("prefer_external_player_1")).toBool();
    const bool built_in_takes_p1 =
        report.value(QStringLiteral("built_in_count")).toInt() > 0 &&
        (!has_external || !prefer_external);
    int external_slot = 0;
    int internal_slot = 0;
    for (const auto& val : devices) {
        const auto item = val.toObject();
        const bool internal = item.value(QStringLiteral("is_built_in")).toBool();
        QString slot;
        if (internal) {
            // Built-in is never Player 2; external-first ON leaves it unassigned.
            slot = built_in_takes_p1 && internal_slot++ == 0
                       ? QStringLiteral("Player 1")
                       : QStringLiteral("Unassigned");
        } else {
            // When built-in is P1, first external controller becomes P2.
            const int index = (built_in_takes_p1 ? 2 : 1) + external_slot++;
            slot = index <= 2 ? QStringLiteral("Player %1").arg(index)
                              : QStringLiteral("Unassigned (two-player preview limit)");
        }
        lines << QStringLiteral("• %1 — %2; %3; %4")
                     .arg(item.value(QStringLiteral("name")).toString(),
                          internal ? QStringLiteral("built-in") : QStringLiteral("external"),
                          item.value(QStringLiteral("transport")).toString(), slot);
    }
    if (report.value(QStringLiteral("ambiguous_identity")).toBool())
        lines << QStringLiteral("Identity ambiguous: automatic assignment will not run.");
    if (!report.value(QStringLiteral("note")).toString().isEmpty())
        lines << QStringLiteral("Note: ") + report.value(QStringLiteral("note")).toString();
    lines << QStringLiteral("Player slots are provisional until validated and applied.")
          << QStringLiteral("Built-in is never Player 2. Prefer external ON: external P1; OFF: built-in P1 and external P2.")
          << QStringLiteral("Physical source and emulated target are never assigned twice.");
    return lines.join(QChar(u'\n'));
}

bool MaybeApply(const InputCommon::InputSubsystem& input, Core::System& system,
                QString* reason) {
    auto say = [reason](const QString& message) {
        if (reason) *reason = message;
        // The idle timer can otherwise disable itself without showing why.
        // Write only when the outcome changes, not on every 2.5-second tick.
        QSettings status = Preferences();
        if (status.value(QStringLiteral("last_routing_result")).toString() != message) {
            status.setValue(QStringLiteral("last_routing_result"), message);
        }
    };
    if (suppress_auto_after_stock_reset) {
        say(QStringLiteral("Stock settings restored; auto assignment deferred until next launch"));
        return false;
    }
    QSettings prefs = Preferences();
    if (prefs.value(QStringLiteral("reset_stock_pending_next_launch"), false).toBool()) {
        prefs.remove(QStringLiteral("reset_stock_pending_next_launch"));
        prefs.setValue(QStringLiteral("automatic_player_assignment"), true);
        // Allow one subsequent launch after Reset to Defaults to detect fresh settings.
    }
    if (!prefs.value(QStringLiteral("automatic_player_assignment"), true).toBool()) {
        say(QStringLiteral("Automatic mapping disabled in preferences"));
        return false;
    }
    const ScanResult scan = Scan(input);
    if (scan.ambiguous_virtual_builtin) {
        say(scan.note);
        return false;
    }
    // Never silently treat a physically connected external Steam Controller
    // as the built-in Odin gamepad. Wait until the actual USB controller is
    // exposed to SDL before replacing the saved P1/P2 bindings.
    const bool steam_visible_in_sdl = std::any_of(
        scan.devices.begin(), scan.devices.end(), [](const Candidate& item) {
            return !item.built_in &&
                   item.device.Get("vendor", "") == "10462" &&
                   item.device.Get("product", "") == "4866";
        });
    if (!steam_visible_in_sdl && !SteamUsbHidNodes().isEmpty()) {
        say(QStringLiteral(
            "USB Steam Controller detected by kernel, not by SDL. "
            "Keeping existing P1/P2 mappings; cannot assign external controller yet."));
        return false;
    }
    if (scan.devices.empty()) {
        say(QStringLiteral("No SDL gamepads available; existing mappings untouched"));
        return false;
    }

    const QString last_p1 = prefs.value(QStringLiteral("last_p1_hash")).toString();
    const QString last_p2 = prefs.value(QStringLiteral("last_p2_hash")).toString();
    const bool takeover = prefs.value(QStringLiteral("explicit_takeover"), false).toBool();
    if (!takeover && last_p1.isEmpty() && ExistingControllerMappings()) {
        // Preserve user consent; this check only pauses routing.
        say(QStringLiteral("Existing manual gamepad configuration preserved; enable auto assignment explicitly"));
        return false;
    }
    const bool prefer = prefs.value(QStringLiteral("prefer_external_player_1"), true).toBool();
    const QString sig = Signature(scan, prefer);
    const bool topology_unchanged =
        sig == prefs.value(QStringLiteral("last_signature")).toString();

    // A genuine controller hotplug is an automatic routing event.
    // Only pause for changed mappings when the device lineup is unchanged.
    const QString current_p1 = PlayerHash(0);
    const QString current_p2 = PlayerHash(1);
    if (!takeover && !last_p1.isEmpty() && topology_unchanged &&
        (last_p1 != current_p1 || last_p2 != current_p2)) {
        // Diagnostic only: identify which mapping changed without altering routing.
        say(QStringLiteral(
            "Manual controller changes detected (P1: %1; P2: %2); automatic mapping paused")
                .arg(last_p1 == current_p1 ? QStringLiteral("same") : QStringLiteral("changed"),
                     last_p2 == current_p2 ? QStringLiteral("same") : QStringLiteral("changed")));
        return false;
    }
    if (!takeover && topology_unchanged) {
        say(QStringLiteral("Assignments already current"));
        return false;
    }

    std::vector<const Candidate*> external, built_in;
    for (const auto& candidate : scan.devices) {
        if (candidate.built_in) built_in.push_back(&candidate);
        else external.push_back(&candidate);
    }
    std::vector<const Candidate*> selected;
    if (external.empty()) {
        // No external controller: built-in P1, with P2 unassigned.
        if (!built_in.empty())
            selected.push_back(built_in.front());
    } else if (!prefer && !built_in.empty()) {
        // TV multiplayer: built-in P1, first external P2.
        selected.push_back(built_in.front());
        selected.insert(selected.end(), external.begin(), external.end());
    } else {
        // Default: external P1 and second external P2, built-in unassigned.
        selected = external;
    }
    if (selected.empty()) {
        say(QStringLiteral("No assignable gamepads"));
        return false;
    }
    const Candidate* p1 = selected.front();
    const Candidate* p2 = selected.size() > 1 ? selected[1] : nullptr;
    // Built-in may only be Player 1, never Player 2; when external-first is
    // enabled and an external pad is present, built-in must be unassigned.
    if ((p1->built_in && prefer && !external.empty()) || (p2 && p2->built_in)) {
        say(QStringLiteral("Invalid handheld routing; existing mappings untouched"));
        return false;
    }
    // Validate the selected devices before clearing even one existing binding.
    const auto has_maps = [&input](const Candidate* item) {
        return !item || (!input.GetButtonMappingForDevice(item->device).empty() &&
                         !input.GetAnalogMappingForDevice(item->device).empty());
    };
    if (!has_maps(p1) || !has_maps(p2)) {
        say(QStringLiteral("A selected controller has no SDL button/stick mapping; no changes made"));
        return false;
    }

    MapPlayer(0, p1, input);
    MapPlayer(1, p2, input);
    system.HIDCore().ReloadInputDevices();
    prefs.setValue(QStringLiteral("last_signature"), sig);
    prefs.setValue(QStringLiteral("last_p1_hash"), PlayerHash(0));
    prefs.setValue(QStringLiteral("last_p2_hash"), PlayerHash(1));
    prefs.remove(QStringLiteral("explicit_takeover"));
    say(QStringLiteral("Assigned Player 1: %1; Player 2: %2")
            .arg(p1->name, p2 ? p2->name : QStringLiteral("none")));
    return true;
}

void RecordAutomaticBaseline() {
    QSettings prefs = Preferences();
    if (!prefs.value(QStringLiteral("automatic_player_assignment"), true).toBool())
        return;
    if (prefs.value(QStringLiteral("last_signature")).toString().isEmpty())
        return;

    // Called only after a successful automatic assignment has been saved.
    // Never rebaseline a manual edit or an unchanged-topology routing check.
    prefs.setValue(QStringLiteral("last_p1_hash"), PlayerHash(0));
    prefs.setValue(QStringLiteral("last_p2_hash"), PlayerHash(1));
    prefs.sync();
}

} // namespace ControllerRouting
