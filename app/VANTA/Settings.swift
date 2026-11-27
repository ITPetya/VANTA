import Foundation

/// Keys for user settings stored in UserDefaults (editable in the app).
enum SettingsKey {
    /// Base URL of the VANTA server. Intentionally has no default in code.
    static let serverURL = "serverURL"
    /// Briefing times and quiet hours, stored as minutes since midnight.
    static let morningMinutes = "briefingMorningMinutes"
    static let breakMinutes = "briefingBreakMinutes"
    static let eveningMinutes = "briefingEveningMinutes"
    static let quietStartMinutes = "quietStartMinutes"
    static let quietEndMinutes = "quietEndMinutes"
    static let notificationsEnabled = "notificationsEnabled"
}

/// Start values (see ROADMAP: 07:00, 12:30, 21:00). Quiet hours are a
/// provisional default until the push budget is decided.
enum SettingsDefault {
    static let morningMinutes = 7 * 60
    static let breakMinutes = 12 * 60 + 30
    static let eveningMinutes = 21 * 60
    static let quietStartMinutes = 22 * 60
    static let quietEndMinutes = 6 * 60 + 30
}

/// Quiet hours as a daily window that may wrap around midnight.
struct QuietHours {
    let startMinutes: Int
    let endMinutes: Int

    /// True if `minutes` (since midnight) lies in [start, end). Equal start
    /// and end means no quiet hours.
    func contains(minutes: Int) -> Bool {
        if startMinutes == endMinutes { return false }
        if startMinutes < endMinutes {
            return minutes >= startMinutes && minutes < endMinutes
        }
        return minutes >= startMinutes || minutes < endMinutes
    }
}
