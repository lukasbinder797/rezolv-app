import SwiftUI
import WebKit
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

#if os(iOS)
struct RezolvWebView: UIViewRepresentable {
    var onNativeNotification: (String, String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onNativeNotification: onNativeNotification)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "rezolvNative")

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.allowsInlineMediaPlayback = true
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.scrollView.bounces = true
        webView.scrollView.showsVerticalScrollIndicator = false
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.953, green: 0.973, blue: 0.980, alpha: 1.0)

        let refresh = UIRefreshControl()
        refresh.tintColor = UIColor(red: 0.063, green: 0.247, blue: 0.435, alpha: 1.0)
        refresh.addTarget(context.coordinator, action: #selector(Coordinator.handleRefresh(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refresh
        context.coordinator.webView = webView

        if let bundleURL = Bundle.main.url(forResource: "RezolvAppBundle", withExtension: "html") {
            webView.loadFileURL(bundleURL, allowingReadAccessTo: bundleURL.deletingLastPathComponent())
        } else if let fallbackURL = URL(string: "http://localhost:8787") {
            webView.load(URLRequest(url: fallbackURL))
        }

        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        let onNativeNotification: (String, String) -> Void

        init(onNativeNotification: @escaping (String, String) -> Void) {
            self.onNativeNotification = onNativeNotification
        }

        @objc func handleRefresh(_ sender: UIRefreshControl) {
            let impact = UIImpactFeedbackGenerator(style: .light)
            impact.impactOccurred()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                sender.endRefreshing()
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "rezolvNative",
                  let dict = message.body as? [String: Any],
                  let type = dict["type"] as? String else {
                return
            }

            if type == "haptic" {
                let styleStr = (dict["style"] as? String) ?? "light"
                let style: UIImpactFeedbackGenerator.FeedbackStyle = (styleStr == "medium") ? .medium : .light
                let generator = UIImpactFeedbackGenerator(style: style)
                generator.impactOccurred()
            } else if type == "notify" {
                let title = (dict["title"] as? String) ?? "REZOLV Sibiu"
                let body = (dict["body"] as? String) ?? ""
                let notifGen = UINotificationFeedbackGenerator()
                notifGen.notificationOccurred(.success)
                RezolvNotificationDelegate.shared.scheduleLocalBanner(title: title, body: body)
                DispatchQueue.main.async {
                    self.onNativeNotification(title, body)
                }
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }

            let scheme = (url.scheme ?? "").lowercased()
            let host = (url.host ?? "").lowercased()

            if scheme == "tel" || scheme == "mailto" || scheme == "waze" || scheme == "maps"
                || host.contains("waze.com") || host.contains("google.com") || host.contains("maps.apple.com") {
                if UIApplication.shared.canOpenURL(url) {
                    UIApplication.shared.open(url, options: [:], completionHandler: nil)
                }
                decisionHandler(.cancel)
                return
            }

            decisionHandler(.allow)
        }

        func webView(
            _ webView: WKWebView,
            runJavaScriptConfirmPanelWithMessage message: String,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping (Bool) -> Void
        ) {
            let alert = UIAlertController(title: "REZOLV Sibiu", message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Anulează", style: .cancel) { _ in completionHandler(false) })
            alert.addAction(UIAlertAction(title: "Confirmă", style: .default) { _ in completionHandler(true) })
            if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
               let rootVC = scene.windows.first?.rootViewController {
                rootVC.present(alert, animated: true)
            } else {
                completionHandler(true)
            }
        }

        func webView(
            _ webView: WKWebView,
            runJavaScriptAlertPanelWithMessage message: String,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping () -> Void
        ) {
            let alert = UIAlertController(title: "REZOLV Sibiu", message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
            if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
               let rootVC = scene.windows.first?.rootViewController {
                rootVC.present(alert, animated: true)
            } else {
                completionHandler()
            }
        }
    }
}
#elseif os(macOS)
struct RezolvWebView: NSViewRepresentable {
    var onNativeNotification: (String, String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onNativeNotification: onNativeNotification)
    }

    func makeNSView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "rezolvNative")

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        context.coordinator.webView = webView

        if let bundleURL = Bundle.main.url(forResource: "RezolvAppBundle", withExtension: "html") {
            webView.loadFileURL(bundleURL, allowingReadAccessTo: bundleURL.deletingLastPathComponent())
        } else if let fallbackURL = URL(string: "http://localhost:8787") {
            webView.load(URLRequest(url: fallbackURL))
        }

        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        let onNativeNotification: (String, String) -> Void

        init(onNativeNotification: @escaping (String, String) -> Void) {
            self.onNativeNotification = onNativeNotification
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "rezolvNative",
                  let dict = message.body as? [String: Any],
                  let type = dict["type"] as? String else {
                return
            }

            if type == "haptic" {
                NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now)
            } else if type == "notify" {
                let title = (dict["title"] as? String) ?? "REZOLV Sibiu"
                let body = (dict["body"] as? String) ?? ""
                NSHapticFeedbackManager.defaultPerformer.perform(.levelChange, performanceTime: .now)
                RezolvNotificationDelegate.shared.scheduleLocalBanner(title: title, body: body)
                DispatchQueue.main.async {
                    self.onNativeNotification(title, body)
                }
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }

            let scheme = (url.scheme ?? "").lowercased()
            let host = (url.host ?? "").lowercased()

            if scheme == "tel" || scheme == "mailto" || scheme == "waze" || scheme == "maps"
                || host.contains("waze.com") || host.contains("google.com") || host.contains("maps.apple.com") {
                NSWorkspace.shared.open(url)
                decisionHandler(.cancel)
                return
            }

            decisionHandler(.allow)
        }

        func webView(
            _ webView: WKWebView,
            runJavaScriptConfirmPanelWithMessage message: String,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping (Bool) -> Void
        ) {
            let alert = NSAlert()
            alert.messageText = "REZOLV Sibiu"
            alert.informativeText = message
            alert.addButton(withTitle: "Confirmă")
            alert.addButton(withTitle: "Anulează")
            let response = alert.runModal()
            completionHandler(response == .alertFirstButtonReturn)
        }

        func webView(
            _ webView: WKWebView,
            runJavaScriptAlertPanelWithMessage message: String,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping () -> Void
        ) {
            let alert = NSAlert()
            alert.messageText = "REZOLV Sibiu"
            alert.informativeText = message
            alert.addButton(withTitle: "OK")
            alert.runModal()
            completionHandler()
        }
    }
}
#endif
