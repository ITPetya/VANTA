import SwiftData
import SwiftUI

@main
struct VANTAApp: App {
    private let container: ModelContainer
    @StateObject private var health: HealthKitManager

    init() {
        // Failing to open the local buffer must not be silent: data would be lost.
        let container: ModelContainer
        do {
            container = try ModelContainer(for: HealthSampleRecord.self)
        } catch {
            fatalError("Local buffer could not be opened: \(error)")
        }
        self.container = container
        let manager = HealthKitManager(container: container)
        _health = StateObject(wrappedValue: manager)
        // Observers must be registered at every launch, also background launches.
        Task { @MainActor in manager.startObserving() }
    }

    var body: some Scene {
        WindowGroup {
            StatusView(health: health)
                .task { await health.refreshAuthorizationState() }
        }
        .modelContainer(container)
    }
}
