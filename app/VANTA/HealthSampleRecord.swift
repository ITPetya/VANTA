import Foundation
import SwiftData

/// Upload state of a locally buffered sample. Only `pending` exists until
/// the server connection is built; the field is there so nothing is lost and
/// nothing is uploaded twice later.
enum UploadStatus: String, Codable {
    case pending
    case uploaded
}

/// The HealthKit data types VANTA reads (read-only).
enum HealthMetric: String, Codable, CaseIterable, Identifiable {
    case sleep
    case heartRate
    case hrv
    case restingHeartRate
    case bodyMass
    case steps

    var id: String { rawValue }

    var title: String {
        switch self {
        case .sleep: "Schlaf"
        case .heartRate: "Herzfrequenz"
        case .hrv: "HRV"
        case .restingHeartRate: "Ruhepuls"
        case .bodyMass: "Gewicht"
        case .steps: "Schritte"
        }
    }

    var unitLabel: String {
        switch self {
        case .sleep: "Schlafphase"
        case .heartRate, .restingHeartRate: "Schläge/min"
        case .hrv: "ms"
        case .bodyMass: "kg"
        case .steps: "Schritte"
        }
    }
}

/// One buffered HealthKit sample. `id` is the upload ID (stable, unique);
/// `healthKitUUID` makes re-processing the same sample a no-op (idempotent).
@Model
final class HealthSampleRecord {
    var id: UUID
    var healthKitUUID: String
    var metricRaw: String
    var value: Double
    var startDate: Date
    var endDate: Date
    var createdAt: Date
    var statusRaw: String

    init(healthKitUUID: String, metric: HealthMetric, value: Double, startDate: Date, endDate: Date) {
        self.id = UUID()
        self.healthKitUUID = healthKitUUID
        self.metricRaw = metric.rawValue
        self.value = value
        self.startDate = startDate
        self.endDate = endDate
        self.createdAt = Date()
        self.statusRaw = UploadStatus.pending.rawValue
    }

    var metric: HealthMetric? { HealthMetric(rawValue: metricRaw) }
    var status: UploadStatus { UploadStatus(rawValue: statusRaw) ?? .pending }
}
