import Foundation
import HealthKit
import SwiftData

/// Reads HealthKit (read-only), receives background deliveries and writes new
/// samples into the local SwiftData buffer. No network access.
@MainActor
final class HealthKitManager: ObservableObject {
    static let lastDeliveryKey = "healthLastBackgroundDelivery"

    private let store = HKHealthStore()
    private let context: ModelContext
    private var observersStarted = false

    @Published var isAvailable = HKHealthStore.isHealthDataAvailable()
    /// True while iOS has not yet asked the user for the read permission.
    /// (iOS hides whether read access was denied, so this is all we can know.)
    @Published var needsAuthorization = false
    @Published var lastDelivery: Date? = UserDefaults.standard.object(forKey: HealthKitManager.lastDeliveryKey) as? Date
    @Published var lastError: String?

    init(container: ModelContainer) {
        self.context = container.mainContext
    }

    // MARK: Types

    private func sampleType(for metric: HealthMetric) -> HKSampleType {
        switch metric {
        case .sleep: HKCategoryType(.sleepAnalysis)
        case .heartRate: HKQuantityType(.heartRate)
        case .hrv: HKQuantityType(.heartRateVariabilitySDNN)
        case .restingHeartRate: HKQuantityType(.restingHeartRate)
        case .bodyMass: HKQuantityType(.bodyMass)
        case .steps: HKQuantityType(.stepCount)
        }
    }

    private var readTypes: Set<HKObjectType> {
        Set(HealthMetric.allCases.map { sampleType(for: $0) })
    }

    // MARK: Authorization

    func refreshAuthorizationState() async {
        guard isAvailable else { return }
        do {
            let status = try await store.statusForAuthorizationRequest(toShare: [], read: readTypes)
            needsAuthorization = (status == .shouldRequest)
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Asks for read access only (toShare is empty) and starts observing.
    func requestAuthorizationAndStart() async {
        guard isAvailable else { return }
        do {
            try await store.requestAuthorization(toShare: [], read: readTypes)
            await refreshAuthorizationState()
            startObserving()
        } catch {
            lastError = error.localizedDescription
        }
    }

    // MARK: Observing

    /// Registers observer queries and background delivery. Must also be
    /// called on every app launch (including background launches by HealthKit).
    func startObserving() {
        guard isAvailable, !observersStarted else { return }
        observersStarted = true
        for metric in HealthMetric.allCases {
            let type = sampleType(for: metric)
            let query = HKObserverQuery(sampleType: type, predicate: nil) { [weak self] _, completion, error in
                guard let self else { completion(); return }
                if let error {
                    Task { @MainActor in self.lastError = error.localizedDescription }
                    completion()
                    return
                }
                Task { @MainActor in
                    await self.fetchNewSamples(for: metric)
                    self.markDelivery()
                    completion()
                }
            }
            store.execute(query)
            // Failure is non-fatal: without the background-delivery entitlement
            // the app still updates while it is open.
            store.enableBackgroundDelivery(for: type, frequency: .immediate) { [weak self] _, error in
                if let error {
                    Task { @MainActor in self?.lastError = "Hintergrundzustellung: \(error.localizedDescription)" }
                }
            }
        }
    }

    private func markDelivery() {
        let now = Date()
        lastDelivery = now
        UserDefaults.standard.set(now, forKey: Self.lastDeliveryKey)
    }

    // MARK: Fetching

    private func anchorKey(_ metric: HealthMetric) -> String { "healthAnchor.\(metric.rawValue)" }

    private func loadAnchor(_ metric: HealthMetric) -> HKQueryAnchor? {
        guard let data = UserDefaults.standard.data(forKey: anchorKey(metric)) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    private func saveAnchor(_ anchor: HKQueryAnchor, for metric: HealthMetric) {
        if let data = try? NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true) {
            UserDefaults.standard.set(data, forKey: anchorKey(metric))
        }
    }

    private func fetchNewSamples(for metric: HealthMetric) async {
        let type = sampleType(for: metric)
        let anchor = loadAnchor(metric)
        let result: ([HKSample], HKQueryAnchor?)? = await withCheckedContinuation { continuation in
            let query = HKAnchoredObjectQuery(type: type, predicate: nil, anchor: anchor, limit: HKObjectQueryNoLimit) {
                _, added, _, newAnchor, error in
                continuation.resume(returning: error == nil ? (added ?? [], newAnchor) : nil)
            }
            store.execute(query)
        }
        guard let (samples, newAnchor) = result else { return }

        for sample in samples {
            insertIfNew(sample, metric: metric)
        }
        do {
            try context.save()
            // Anchor is advanced only after the samples are safely stored.
            if let newAnchor { saveAnchor(newAnchor, for: metric) }
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func insertIfNew(_ sample: HKSample, metric: HealthMetric) {
        let uuid = sample.uuid.uuidString
        var descriptor = FetchDescriptor<HealthSampleRecord>(predicate: #Predicate { $0.healthKitUUID == uuid })
        descriptor.fetchLimit = 1
        if let existing = try? context.fetch(descriptor), !existing.isEmpty { return }

        let value: Double
        switch sample {
        case let quantity as HKQuantitySample:
            value = Self.value(of: quantity, metric: metric)
        case let category as HKCategorySample:
            value = Double(category.value)
        default:
            return
        }
        context.insert(HealthSampleRecord(
            healthKitUUID: uuid, metric: metric, value: value,
            startDate: sample.startDate, endDate: sample.endDate
        ))
    }

    private static func value(of sample: HKQuantitySample, metric: HealthMetric) -> Double {
        switch metric {
        case .heartRate, .restingHeartRate:
            sample.quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))
        case .hrv:
            sample.quantity.doubleValue(for: .secondUnit(with: .milli))
        case .bodyMass:
            sample.quantity.doubleValue(for: .gramUnit(with: .kilo))
        case .steps, .sleep:
            sample.quantity.doubleValue(for: .count())
        }
    }
}
