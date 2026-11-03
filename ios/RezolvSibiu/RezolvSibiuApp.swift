import SwiftUI
import UserNotifications
#if os(macOS)
import AppKit
#endif

final class RezolvNotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    static let shared = RezolvNotificationDelegate()

    func requestAuthorization() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    func scheduleLocalBanner(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 0.2, repeats: false)
        let req = UNNotificationRequest(
            identifier: "rezolv-\(UUID().uuidString)",
            content: content,
            trigger: trigger
        )
        UNUserNotificationCenter.current().add(req, withCompletionHandler: nil)
    }

    // Show notification banner + sound even when the app is active in foreground
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }
}

@main
struct RezolvSibiuApp: App {
    init() {
        RezolvNotificationDelegate.shared.requestAuthorization()
        #if os(macOS)
        DispatchQueue.main.async {
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
        #endif
    }

    var body: some Scene {
        WindowGroup("REZOLV Sibiu — iOS MVP") {
            ContentView()
                .preferredColorScheme(.light)
                #if os(macOS)
                .frame(minWidth: 412, idealWidth: 420, maxWidth: 460, minHeight: 780, idealHeight: 860)
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 420, height: 860)
        #endif
    }
}
