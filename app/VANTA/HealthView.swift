import SwiftData
import SwiftUI

/// Health section of the start screen: permission state, latest value per
/// type, buffer size and time of the last background delivery.
struct HealthSection: View {
    @ObservedObject var manager: HealthKitManager
    @Query(sort: \HealthSampleRecord.startDate, order: .reverse) private var samples: [HealthSampleRecord]

    var body: some View {
        Section("Gesundheit") {
            if !manager.isAvailable {
                Label("HealthKit ist auf diesem Gerät nicht verfügbar.", systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            } else if manager.needsAuthorization {
                Label("HealthKit-Berechtigung fehlt.", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Button("Zugriff anfragen") {
                    Task { await manager.requestAuthorizationAndStart() }
                }
            } else if samples.isEmpty {
                Text("Noch keine Werte. Falls dauerhaft leer: Zugriff in Einstellungen > Gesundheit > Datenzugriff prüfen.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            ForEach(HealthMetric.allCases) { metric in
                LabeledContent(metric.title) {
                    if let latest = samples.first(where: { $0.metricRaw == metric.rawValue }) {
                        VStack(alignment: .trailing) {
                            Text(format(latest, metric: metric))
                            Text(latest.endDate, style: .relative)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("kein Wert").foregroundStyle(.secondary)
                    }
                }
            }
            LabeledContent("Im Zwischenspeicher") {
                Text("\(samples.filter { $0.status == .pending }.count) nicht hochgeladen")
            }
            LabeledContent("Letzte Hintergrundzustellung") {
                if let last = manager.lastDelivery {
                    Text(last, style: .relative)
                } else {
                    Text("noch keine")
                }
            }
            if let error = manager.lastError {
                Text(error).font(.footnote).foregroundStyle(.red)
            }
        }
    }

    private func format(_ sample: HealthSampleRecord, metric: HealthMetric) -> String {
        switch metric {
        case .sleep: "Phase \(Int(sample.value))"
        case .steps: "\(Int(sample.value)) \(metric.unitLabel)"
        default: String(format: "%.1f %@", sample.value, metric.unitLabel)
        }
    }
}
