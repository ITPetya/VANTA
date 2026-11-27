import SwiftData
import SwiftUI

/// Latest feedback entries for our own notifications.
struct FeedbackSection: View {
    @Query(sort: \FeedbackRecord.eventDate, order: .reverse) private var entries: [FeedbackRecord]

    var body: some View {
        Section("Feedback zu Meldungen") {
            if entries.isEmpty {
                Text("Noch kein Feedback.").foregroundStyle(.secondary)
            }
            ForEach(entries.prefix(20)) { entry in
                VStack(alignment: .leading) {
                    HStack {
                        Text(entry.event?.title ?? entry.eventRaw)
                        Spacer()
                        Text(entry.eventDate, format: .dateTime.day().month().hour().minute())
                            .foregroundStyle(.secondary)
                    }
                    if let seconds = entry.secondsToOpen {
                        Text("Geöffnet nach \(Int(seconds)) s")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(entry.status == .pending ? "nicht hochgeladen" : "hochgeladen")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// Settings for briefing times and quiet hours.
struct NotificationSettingsSection: View {
    @ObservedObject var manager: NotificationManager
    @AppStorage(SettingsKey.notificationsEnabled) private var enabled = true
    @AppStorage(SettingsKey.morningMinutes) private var morning = SettingsDefault.morningMinutes
    @AppStorage(SettingsKey.breakMinutes) private var pause = SettingsDefault.breakMinutes
    @AppStorage(SettingsKey.eveningMinutes) private var evening = SettingsDefault.eveningMinutes
    @AppStorage(SettingsKey.quietStartMinutes) private var quietStart = SettingsDefault.quietStartMinutes
    @AppStorage(SettingsKey.quietEndMinutes) private var quietEnd = SettingsDefault.quietEndMinutes

    var body: some View {
        Section("Benachrichtigungen") {
            if manager.authorization == .notDetermined {
                Button("Berechtigung anfragen") { Task { await manager.requestAuthorization() } }
            } else if manager.authorization == .denied {
                Label("Benachrichtigungen sind in den iOS-Einstellungen ausgeschaltet.", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
            }
            Toggle("Briefings planen", isOn: $enabled)
            timePicker("Morgen", minutes: $morning)
            timePicker("Pause", minutes: $pause)
            timePicker("Abend", minutes: $evening)
            timePicker("Ruhezeit ab", minutes: $quietStart)
            timePicker("Ruhezeit bis", minutes: $quietEnd)
            Text("Briefings in der Ruhezeit werden nicht zugestellt.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            if let error = manager.lastError {
                Text(error).font(.footnote).foregroundStyle(.red)
            }
        }
        .onChange(of: enabled) { _, _ in Task { await manager.reschedule() } }
        .onChange(of: morning) { _, _ in Task { await manager.reschedule() } }
        .onChange(of: pause) { _, _ in Task { await manager.reschedule() } }
        .onChange(of: evening) { _, _ in Task { await manager.reschedule() } }
        .onChange(of: quietStart) { _, _ in Task { await manager.reschedule() } }
        .onChange(of: quietEnd) { _, _ in Task { await manager.reschedule() } }
    }

    private func timePicker(_ title: String, minutes: Binding<Int>) -> some View {
        DatePicker(title, selection: Binding(
            get: {
                Calendar.current.date(bySettingHour: minutes.wrappedValue / 60, minute: minutes.wrappedValue % 60, second: 0, of: Date()) ?? Date()
            },
            set: { date in
                let parts = Calendar.current.dateComponents([.hour, .minute], from: date)
                minutes.wrappedValue = (parts.hour ?? 0) * 60 + (parts.minute ?? 0)
            }
        ), displayedComponents: .hourAndMinute)
    }
}
