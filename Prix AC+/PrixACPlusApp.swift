import SwiftUI

@main
struct PrixACPlusApp: App {
    @StateObject private var appSettings: AppSettings = AppSettings()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appSettings)
        }
    }
}
