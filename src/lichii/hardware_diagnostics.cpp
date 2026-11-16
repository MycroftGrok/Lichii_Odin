// SPDX-FileCopyrightText: Copyright 2026 Lichii Odin contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "hardware_diagnostics.h"
#include "controller_routing.h"
#include "handheld_profiles.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSaveFile>
#include <QScreen>
#include <QStringList>
#include <QStorageInfo>
#include <QSysInfo>
#include <QThread>
#include <limits>

#include "common/param_package.h"
#include "input_common/main.h"
#include "qt_common/util/vk.h"

namespace {
QString SmallFile(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 1024 * 1024)
        return {};
    QString content = QString::fromUtf8(file.readAll());
    content.replace(QChar::Null, QChar(u' '));
    return content.trimmed();
}

QString CpuModel(const QJsonObject& handheld) {
#ifdef Q_OS_LINUX
    const QString cpuinfo = SmallFile(QStringLiteral("/proc/cpuinfo"));
    const QRegularExpression model_pattern(
        QStringLiteral(R"((?:^|\n)(?:model name|Hardware|Processor)\s*:\s*([^\r\n]+))"),
        QRegularExpression::CaseInsensitiveOption);
    auto matches = model_pattern.globalMatch(cpuinfo);
    while (matches.hasNext()) {
        const QString value = matches.next().captured(1).trimmed();
        // On aarch64, /proc/cpuinfo "processor : 0" is an INDEX, not
        // a CPU model. Older code incorrectly displayed CPU: 0.
        if (value.size() > 2 && value.contains(QRegularExpression(
                QStringLiteral(R"([A-Za-z])"))))
            return value;
    }
#endif
    const QString chipset = handheld.value(QStringLiteral("chipset")).toString();
    if (chipset == QStringLiteral("Qualcomm Snapdragon 8 Elite"))
        return QStringLiteral("Qualcomm Oryon (Snapdragon 8 Elite; catalog identification)");
    if (!chipset.isEmpty())
        return chipset + QStringLiteral(" (CPU name unavailable; SoC identified)");
    return QStringLiteral("ARM CPU (model unavailable)");
}

QString TotalRam() {
#ifdef Q_OS_LINUX
    const QString text = SmallFile(QStringLiteral("/proc/meminfo"));
    const QRegularExpression re(QStringLiteral(R"((?m)^MemTotal:\s*(\d+)\s+kB)"));
    const auto match = re.match(text);
    if (match.hasMatch()) {
        bool ok = false;
        const quint64 kib = match.captured(1).toULongLong(&ok);
        if (ok && kib <= (std::numeric_limits<quint64>::max() / 1024))
            return QString::number(kib * 1024);
    }
#endif
    return {};
}

QString SizeText(const QString& raw) {
    bool ok = false;
    const auto bytes = raw.toULongLong(&ok);
    return ok ? QStringLiteral("%1 GiB").arg(QString::number(
                    static_cast<double>(bytes) / (1024.0 * 1024 * 1024), 'f', 2))
              : QStringLiteral("Unavailable");
}

QString ScreenMaxMode(const QString& connector) {
#ifdef Q_OS_LINUX
    if (connector.isEmpty())
        return QStringLiteral("Unavailable");
    QDir drm(QStringLiteral("/sys/class/drm"));
    int best_width = 0, best_height = 0;
    for (const auto& entry : drm.entryList(QDir::AllDirs | QDir::System | QDir::NoDotAndDotDot)) {
        if (!entry.startsWith(QStringLiteral("card")) ||
            !entry.endsWith(QStringLiteral("-") + connector))
            continue;
        const QStringList modes = SmallFile(drm.filePath(entry + QStringLiteral("/modes")))
                                      .split(QChar(u'\n'), Qt::SkipEmptyParts);
        const QRegularExpression regex(QStringLiteral(R"(^([0-9]+)x([0-9]+)$)"));
        for (const auto& line : modes) {
            const auto match = regex.match(line.trimmed());
            if (!match.hasMatch())
                continue;
            const int width = match.captured(1).toInt();
            const int height = match.captured(2).toInt();
            if (static_cast<qint64>(width) * height >
                static_cast<qint64>(best_width) * best_height) {
                best_width = width;
                best_height = height;
            }
        }
    }
    if (best_width > 0 && best_height > 0)
        return QStringLiteral("%1 x %2 (DRM advertised mode)").arg(best_width).arg(best_height);
#endif
    return QStringLiteral("Unavailable (current resolution shown separately)");
}

QJsonObject Storage(const QString& label, const QString& location) {
    const QStorageInfo disk(location);
    QJsonObject item{{QStringLiteral("label"), label},
                     {QStringLiteral("filesystem_ready"), disk.isReady()},
                     {QStringLiteral("total_bytes"), QString()},
                     {QStringLiteral("available_bytes"), QString()}};
    if (disk.isReady() && disk.isValid() && disk.bytesTotal() >= 0 &&
        disk.bytesAvailable() >= 0) {
        item[QStringLiteral("total_bytes")] = QString::number(disk.bytesTotal());
        item[QStringLiteral("available_bytes")] = QString::number(disk.bytesAvailable());
    }
    return item;
}

} // namespace

namespace HardwareDiagnostics {
QString ReportPath() {
    return QDir::homePath() +
           QStringLiteral("/.local/share/lichii/logs/hardware-detection-latest.json");
}

QJsonObject Collect(const std::vector<VkDeviceInfo::Record>& gpus,
                    const InputCommon::InputSubsystem& input) {
    QJsonObject report;
    report[QStringLiteral("schema_version")] = 1;
    report[QStringLiteral("detected_at")] = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    report[QStringLiteral("operating_system")] = QSysInfo::prettyProductName();
    report[QStringLiteral("architecture")] = QSysInfo::currentCpuArchitecture();
    const auto handheld = HandheldProfiles::Detect();
    report[QStringLiteral("cpu")] = QJsonObject{
        {QStringLiteral("model"), CpuModel(handheld)},
        {QStringLiteral("logical_processors"), QThread::idealThreadCount()}};
    report[QStringLiteral("system_ram_total_bytes")] = TotalRam();
    report[QStringLiteral("handheld_profile")] = handheld;
#ifdef Q_OS_LINUX
    QString soc_model = SmallFile(QStringLiteral("/sys/devices/soc0/machine"));
    if (soc_model.isEmpty())
        soc_model = SmallFile(QStringLiteral("/proc/device-tree/model"));
    report[QStringLiteral("system_on_chip")] =
        soc_model.isEmpty() ? QStringLiteral("Unavailable") : soc_model;
#else
    report[QStringLiteral("system_on_chip")] = QStringLiteral("Unavailable");
#endif

    QJsonArray graphics;
    for (const auto& gpu : gpus) {
        const bool shared = gpu.integrated_gpu;
        graphics.append(QJsonObject{
            {QStringLiteral("name"), QString::fromStdString(gpu.name)},
            {QStringLiteral("integrated_gpu"), shared},
            // This is a Vulkan device-local heap, NOT a dedicated VRAM figure on UMA.
            {QStringLiteral("vulkan_local_heap_bytes"),
             gpu.local_heap_bytes ? QString::number(gpu.local_heap_bytes) : QString()},
            {QStringLiteral("memory_description"),
             shared ? QStringLiteral("Shared system RAM / unified memory; not dedicated VRAM")
                    : QStringLiteral("Vulkan device-local heap; not current free VRAM")}});
    }
    report[QStringLiteral("gpus")] = graphics;

    QJsonArray screens;
    for (const QScreen* screen : QGuiApplication::screens()) {
        screens.append(QJsonObject{
            {QStringLiteral("name"), screen->name()},
            {QStringLiteral("current_logical_resolution"),
             QStringLiteral("%1 x %2").arg(screen->size().width()).arg(screen->size().height())},
            {QStringLiteral("device_pixel_ratio"), screen->devicePixelRatio()},
            {QStringLiteral("max_advertised_resolution"), ScreenMaxMode(screen->name())}});
    }
    report[QStringLiteral("screens")] = screens;

    QJsonArray disks;
    disks.append(Storage(QStringLiteral("Home filesystem"), QDir::homePath()));
    report[QStringLiteral("storage")] = disks;

    QJsonArray mapped;
    for (const auto& device : input.GetInputDevices()) {
        const std::string engine = device.Get("engine", "");
        if (engine != "sdl" && engine != "joycon" && engine != "gcpad")
            continue;
        mapped.append(QJsonObject{{QStringLiteral("name"),
                                    QString::fromStdString(device.Get("display", "Unknown"))},
                                  {QStringLiteral("backend"), QString::fromStdString(engine)}});
    }
    report[QStringLiteral("controllers_usable_by_lichii")] = mapped;
    report[QStringLiteral("controller_assignment")] = ControllerRouting::Inspect(input);

    // Keep physical source devices separate: InputPlumber can exclusively own them.
    // A restricted physical evdev node alone does not mean the emulator is misconfigured.
    QJsonArray kernel;
#ifdef Q_OS_LINUX
    const QDir events(QStringLiteral("/sys/class/input"));
    const auto nodes = events.entryList(QStringList{QStringLiteral("event*")},
                                        QDir::AllDirs | QDir::System | QDir::NoDotAndDotDot);
    for (const auto& node : nodes) {
        const QString name = SmallFile(events.filePath(node + QStringLiteral("/device/name")));
        if (!name.contains(QRegularExpression(
                QStringLiteral("odin|gamepad|controller|xbox|steam deck"),
                QRegularExpression::CaseInsensitiveOption)))
            continue;
        QFile check(QStringLiteral("/dev/input/") + node);
        const bool accessible = check.open(QIODevice::ReadOnly);
        if (accessible)
            check.close();
        kernel.append(QJsonObject{{QStringLiteral("name"), name},
                                  {QStringLiteral("device"), node},
                                  {QStringLiteral("readable_by_process"), accessible}});
    }
    // The Toolbox's /etc belongs to the container. For host-specific
    // ArmadaOS settings, use the officially mounted host filesystem.
    const QString host_mode = report.value(QStringLiteral("controller_assignment"))
                                  .toObject().value(QStringLiteral("armada_controller_mode"))
                                  .toString();
    report[QStringLiteral("armada_controller_mode")] =
        host_mode.isEmpty() ? QStringLiteral("Unavailable") : host_mode;
#else
    report[QStringLiteral("armada_controller_mode")] = QStringLiteral("Not applicable");
#endif
    report[QStringLiteral("kernel_controller_devices")] = kernel;
    report[QStringLiteral("controller_note")] = mapped.isEmpty()
       ? QStringLiteral("No SDL-accessible gamepad listed. Physical nodes may be owned by InputPlumber.")
       : QStringLiteral("SDL/gamepad devices available for Lichii mapping.");
    return report;
}

QString FormatReport(const QJsonObject& report) {
    QStringList lines{QStringLiteral("Lichii — Startup Hardware & Controller Diagnostics"),
                      QStringLiteral("Detected: ") +
                          report.value(QStringLiteral("detected_at")).toString(),
                      QString(), QStringLiteral("SYSTEM"),
                      QStringLiteral("OS: ") + report.value(QStringLiteral("operating_system")).toString(),
                      QStringLiteral("Architecture: ") +
                          report.value(QStringLiteral("architecture")).toString()};
    const auto cpu = report.value(QStringLiteral("cpu")).toObject();
    lines << QStringLiteral("CPU: ") + cpu.value(QStringLiteral("model")).toString()
          << QStringLiteral("Logical processors: %1")
                 .arg(cpu.value(QStringLiteral("logical_processors")).toInt())
          << QStringLiteral("SoC / device model: ") +
                 report.value(QStringLiteral("system_on_chip")).toString()
          << QStringLiteral("System RAM: ") +
                 SizeText(report.value(QStringLiteral("system_ram_total_bytes")).toString())
          << QString() << HandheldProfiles::Format(
                 report.value(QStringLiteral("handheld_profile")).toObject())
          << QString() << QStringLiteral("GRAPHICS");
    const auto gpus = report.value(QStringLiteral("gpus")).toArray();
    if (gpus.isEmpty())
        lines << QStringLiteral("No Vulkan GPU details available");
    for (const auto& value : gpus) {
        const auto gpu = value.toObject();
        lines << QStringLiteral("GPU: ") + gpu.value(QStringLiteral("name")).toString()
              << QStringLiteral("GPU heap: ") +
                     SizeText(gpu.value(QStringLiteral("vulkan_local_heap_bytes")).toString())
              << QStringLiteral("Memory type: ") +
                     gpu.value(QStringLiteral("memory_description")).toString();
    }

    lines << QString() << QStringLiteral("DISPLAYS");
    for (const auto& value : report.value(QStringLiteral("screens")).toArray()) {
        const auto screen = value.toObject();
        lines << QStringLiteral("Display: ") + screen.value(QStringLiteral("name")).toString()
              << QStringLiteral("Current logical: ") +
                     screen.value(QStringLiteral("current_logical_resolution")).toString()
              << QStringLiteral("Maximum mode: ") +
                     screen.value(QStringLiteral("max_advertised_resolution")).toString();
    }
    lines << QString() << QStringLiteral("STORAGE");
    for (const auto& value : report.value(QStringLiteral("storage")).toArray()) {
        const auto disk = value.toObject();
        lines << disk.value(QStringLiteral("label")).toString() +
                     QStringLiteral(": %1 total, %2 available")
                         .arg(SizeText(disk.value(QStringLiteral("total_bytes")).toString()),
                              SizeText(disk.value(QStringLiteral("available_bytes")).toString()));
    }
    lines << QString() << QStringLiteral("CONTROLLERS")
          << QStringLiteral("ArmadaOS controller mode: ") +
                 report.value(QStringLiteral("armada_controller_mode")).toString();
    const auto available = report.value(QStringLiteral("controllers_usable_by_lichii")).toArray();
    if (available.isEmpty())
        lines << QStringLiteral("No SDL-accessible gamepad found.");
    for (const auto& value : available) {
        const auto item = value.toObject();
        lines << QStringLiteral("Lichii input: ") + item.value(QStringLiteral("name")).toString() +
                     QStringLiteral(" [") + item.value(QStringLiteral("backend")).toString() +
                     QStringLiteral("]");
    }
    for (const auto& value : report.value(QStringLiteral("kernel_controller_devices")).toArray()) {
        const auto item = value.toObject();
        lines << QStringLiteral("Kernel source: ") + item.value(QStringLiteral("name")).toString() +
                     QStringLiteral(" (") + item.value(QStringLiteral("device")).toString() +
                     QStringLiteral(", ") +
                     (item.value(QStringLiteral("readable_by_process")).toBool()
                         ? QStringLiteral("readable") : QStringLiteral("restricted")) +
                     QStringLiteral(")");
    }
    lines << QString() << ControllerRouting::Format(
        report.value(QStringLiteral("controller_assignment")).toObject());
    lines << QStringLiteral("Note: ") +
                 report.value(QStringLiteral("controller_note")).toString()
          << QString() << QStringLiteral("Automatic JSON report: ") + ReportPath()
          << QStringLiteral("Read-only detection. No system settings changed.");
    return lines.join(QChar(u'\n'));
}

bool SaveReport(const QJsonObject& report) {
    const QString path = ReportPath();
    const QFileInfo logdir(QFileInfo(path).absolutePath());
    if (logdir.isSymLink() || QFileInfo(path).isSymLink() ||
        !QDir().mkpath(logdir.absoluteFilePath()))
        return false;
    QSaveFile out(path);
    if (!out.open(QIODevice::WriteOnly))
        return false;
    const QByteArray data = QJsonDocument(report).toJson(QJsonDocument::Indented);
    if (out.write(data) != data.size() || !out.commit())
        return false;
    QFile::setPermissions(path, QFile::ReadOwner | QFile::WriteOwner);
    return true;
}
} // namespace HardwareDiagnostics
