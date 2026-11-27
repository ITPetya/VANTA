import Foundation

/// Connection state shown on the start screen.
enum ServerState {
    case online
    case offline
}

struct SyncStatus {
    let state: ServerState
    let lastSync: Date?

    /// Placeholder data until a real server connection exists (M1).
    static let sample = SyncStatus(
        state: .online,
        lastSync: Date().addingTimeInterval(-15 * 60)
    )
}
