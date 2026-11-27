import Foundation
import SwiftData
import UserNotifications

/// Local notifications only (no Apple Push). Schedules briefings ahead of
/// time, records feedback (delivered, opened, dismissed) into SwiftData.
/// No network access.
@MainActor
final class NotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let categoryID = "vanta.briefing"
    private static let idPrefix = "briefing"
    /// iOS keeps at most 64 pending requests; 3 slots x 7 days = 21.
    private static let daysAhead = 7

    private let center = UNUserNotificationCenter.current()
    private let context: ModelContext

    @Published var authorization: UNAuthorizationStatus = .notDetermined
    @Published var lastError: String?

    init(container: ModelContainer) {
        self.context = container.mainContext
        super.init()
        center.delegate = self
        let category = UNNotificationCategory(
            identifier: Self.categoryID,
            actions: [],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )
        center.setNotificationCategories([category])
    }

    // MARK: Authorization

    func refreshAuthorization() async {
        authorization = await center.notificationSettings().authorizationStatus
    }

    func requestAuthorization() async {
        do {
            _ = try await center.requestAuthorization(options: [.alert, .sound])
        } catch {
            lastError = error.localizedDescription
        }
        await refreshAuthorization()
        await reschedule()
    }

    // MARK: Scheduling

    /// Replaces all pending briefings. Content is fixed when scheduling, so
    /// this runs at launch, on foreground and after settings changes.
    func reschedule(now: Date = Date()) async {
        await refreshAuthorization()
        let defaults = UserDefaults.standard
        let pending = await center.pendingNotificationRequests()
        center.removePendingNotificationRequests(
            withIdentifiers: pending.map(\.identifier).filter { $0.hasPrefix(Self.idPrefix) })
        let enabled = defaults.object(forKey: SettingsKey.notificationsEnabled) as? Bool ?? true
        guard enabled, authorization == .authorized || authorization == .provisional else { return }

        let slots: [(String, Int)] = [
            ("morning", Self.minutes(SettingsKey.morningMinutes, SettingsDefault.morningMinutes)),
            ("break", Self.minutes(SettingsKey.breakMinutes, SettingsDefault.breakMinutes)),
            ("evening", Self.minutes(SettingsKey.eveningMinutes, SettingsDefault.eveningMinutes)),
        ]
        let quiet = QuietHours(
            startMinutes: Self.minutes(SettingsKey.quietStartMinutes, SettingsDefault.quietStartMinutes),
            endMinutes: Self.minutes(SettingsKey.quietEndMinutes, SettingsDefault.quietEndMinutes)
        )
        let body = testBriefingBody()
        let calendar = Calendar.current
        let idFormat = DateFormatter()
        idFormat.dateFormat = "yyyyMMddHHmm"
        idFormat.locale = Locale(identifier: "en_US_POSIX")

        for day in 0..<Self.daysAhead {
            guard let dayDate = calendar.date(byAdding: .day, value: day, to: now) else { continue }
            for (name, minutes) in slots where !quiet.contains(minutes: minutes) {
                var parts = calendar.dateComponents([.year, .month, .day], from: dayDate)
                parts.hour = minutes / 60
                parts.minute = minutes % 60
                guard let fire = calendar.date(from: parts), fire > now else { continue }
                let content = UNMutableNotificationContent()
                content.title = "Testbriefing"
                content.body = body
                content.sound = .default
                content.categoryIdentifier = Self.categoryID
                let id = "\(Self.idPrefix)-\(name)-\(idFormat.string(from: fire))"
                let trigger = UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)
                do {
                    try await center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
                } catch {
                    lastError = error.localizedDescription
                }
            }
        }
    }

    private static func minutes(_ key: String, _ fallback: Int) -> Int {
        UserDefaults.standard.object(forKey: key) as? Int ?? fallback
    }

    /// Test content: latest buffered HealthKit value per type.
    private func testBriefingBody() -> String {
        let descriptor = FetchDescriptor<HealthSampleRecord>(sortBy: [SortDescriptor(\.startDate, order: .reverse)])
        let samples = (try? context.fetch(descriptor)) ?? []
        var parts: [String] = []
        for metric in HealthMetric.allCases {
            guard let latest = samples.first(where: { $0.metricRaw == metric.rawValue }) else { continue }
            switch metric {
            case .sleep: continue
            case .steps: parts.append("\(metric.title) \(Int(latest.value))")
            default: parts.append(String(format: "%@ %.1f %@", metric.title, latest.value, metric.unitLabel))
            }
        }
        return parts.isEmpty ? "Noch keine Gesundheitswerte im Zwischenspeicher." : parts.joined(separator: ", ")
    }

    // MARK: Feedback

    /// Stores one event unless it was already recorded (idempotent).
    private func record(_ event: FeedbackEvent, id: String, date: Date, secondsToOpen: Double? = nil) {
        let raw = event.rawValue
        let descriptor = FetchDescriptor<FeedbackRecord>(
            predicate: #Predicate { $0.notificationID == id && $0.eventRaw == raw }
        )
        if let existing = try? context.fetchCount(descriptor), existing > 0 { return }
        context.insert(FeedbackRecord(notificationID: id, event: event, eventDate: date, secondsToOpen: secondsToOpen))
        do {
            try context.save()
        } catch {
            lastError = "Feedback konnte nicht gespeichert werden: \(error.localizedDescription)"
        }
    }

    /// Notifications delivered while the app was not running are only known
    /// afterwards; pick them up from the notification center at launch.
    func recordDeliveredFromCenter() async {
        for note in await center.deliveredNotifications()
        where note.request.identifier.hasPrefix(Self.idPrefix) {
            record(.delivered, id: note.request.identifier, date: note.date)
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        let id = notification.request.identifier
        let date = notification.date
        await MainActor.run { record(.delivered, id: id, date: date) }
        return [.banner, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let id = response.notification.request.identifier
        let delivered = response.notification.date
        let action = response.actionIdentifier
        let now = Date()
        await MainActor.run {
            // Ensure a delivery entry exists even if the app was not running.
            record(.delivered, id: id, date: delivered)
            switch action {
            case UNNotificationDefaultActionIdentifier:
                record(.opened, id: id, date: now, secondsToOpen: max(0, now.timeIntervalSince(delivered)))
            case UNNotificationDismissActionIdentifier:
                record(.dismissed, id: id, date: now)
            default:
                break
            }
        }
    }
}
