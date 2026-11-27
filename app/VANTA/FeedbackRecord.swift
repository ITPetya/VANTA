import Foundation
import SwiftData

/// What happened to one of our own notifications.
enum FeedbackEvent: String, Codable {
    case delivered
    case opened
    case dismissed

    var title: String {
        switch self {
        case .delivered: "zugestellt"
        case .opened: "geöffnet"
        case .dismissed: "weggewischt"
        }
    }
}

/// One locally stored feedback entry. `id` is the upload ID. The pair
/// (`notificationID`, `eventRaw`) is unique in practice: recording the same
/// event twice is a no-op (idempotent), see NotificationManager.
@Model
final class FeedbackRecord {
    var id: UUID
    var notificationID: String
    var eventRaw: String
    var eventDate: Date
    /// Time from delivery to opening, only set for `opened`.
    var secondsToOpen: Double?
    var createdAt: Date
    var statusRaw: String

    init(notificationID: String, event: FeedbackEvent, eventDate: Date, secondsToOpen: Double? = nil) {
        self.id = UUID()
        self.notificationID = notificationID
        self.eventRaw = event.rawValue
        self.eventDate = eventDate
        self.secondsToOpen = secondsToOpen
        self.createdAt = Date()
        self.statusRaw = UploadStatus.pending.rawValue
    }

    var event: FeedbackEvent? { FeedbackEvent(rawValue: eventRaw) }
    var status: UploadStatus { UploadStatus(rawValue: statusRaw) ?? .pending }
}
