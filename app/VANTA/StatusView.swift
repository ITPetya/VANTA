import SwiftUI

struct StatusView: View {
    @ObservedObject var health: HealthKitManager
    @AppStorage(SettingsKey.serverURL) private var serverURL = ""
    @State private var status = SyncStatus.sample
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    HStack {
                        Image(systemName: status.state == .online ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(status.state == .online ? .green : .red)
                        Text(status.state == .online ? "Online" : "Offline")
                    }
                    LabeledContent("Letzter Sync") {
                        if let last = status.lastSync {
                            Text(last, style: .relative)
                        } else {
                            Text("nie")
                        }
                    }
                    LabeledContent("Adresse") {
                        Text(serverURL.isEmpty ? "nicht eingestellt" : serverURL)
                            .foregroundStyle(.secondary)
                    }
                }
                HealthSection(manager: health)
                Section {
                    Text("Beispieldaten: noch keine Verbindung zum Server.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("VANTA")
            .toolbar {
                Button("Einstellungen", systemImage: "gearshape") { showSettings = true }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
    }
}

struct SettingsView: View {
    @AppStorage(SettingsKey.serverURL) private var serverURL = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("https://", text: $serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .navigationTitle("Einstellungen")
            .toolbar {
                Button("Fertig") { dismiss() }
            }
        }
    }
}
