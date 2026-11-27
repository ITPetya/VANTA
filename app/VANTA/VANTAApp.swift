import SwiftData
import SwiftUI

@main
struct VANTAApp: App {
    private let container: ModelContainer
    @StateObject private var health: HealthKitManager
    @StateObject private var notifications: NotificationManager
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Failing to open the local buffer must not be silent: data would be lost.
        let container: ModelContainer
        do {
            container = try ModelContainer(for: HealthSampleRecord.self, FeedbackRecord.self)
        } catch {
            fatalError("Local buffer could not be opened: \(error)")
        }
        self.container = container
        let manager = HealthKitManager(container: container)
        _health = StateObject(wrappedValue: manager)
        // The delegate must be set at every launch to receive feedback.
        _notifications = StateObject(wrappedValue: NotificationManager(container: container))
        // Observers must be registered at every launch, also background launches.
        Task { @MainActor in manager.startObserving() }
    }

    var body: some Scene {
        WindowGroup {
            StatusView(health: health, notifications: notifications)
                .task {
                    await health.refreshAuthorizationState()
                    await notifications.refreshAuthorization()
                    await notifications.recordDeliveredFromCenter()
                    await notifications.reschedule()
                }
                .onChange(of: scenePhase) { _, phase in
                    guard phase == .active else { return }
                    Task {
                        await notifications.recordDeliveredFromCenter()
                        await notifications.reschedule()
                    }
                }
        }
        .modelContainer(container)
    }
}
