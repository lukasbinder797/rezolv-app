import SwiftUI
import Combine

struct NativeBannerState: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let body: String
}

final class NativeBannerViewModel: ObservableObject {
    @Published var banner: NativeBannerState? = nil
}

struct ContentView: View {
    @StateObject private var viewModel = NativeBannerViewModel()

    var body: some View {
        ZStack(alignment: .top) {
            Color(red: 0.953, green: 0.973, blue: 0.980)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                RezolvWebView(onNativeNotification: { title, message in
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                        viewModel.banner = NativeBannerState(title: title, body: message)
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) {
                        withAnimation(.easeOut(duration: 0.25)) {
                            viewModel.banner = nil
                        }
                    }
                })
                .ignoresSafeArea(edges: .bottom)
            }

            if let activeBanner = viewModel.banner {
                VStack(alignment: .leading, spacing: 4) {
                    Text(activeBanner.title)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(.white)
                    Text(activeBanner.body)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Color.white.opacity(0.92))
                        .lineLimit(2)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color(red: 0.063, green: 0.247, blue: 0.435))
                        .shadow(color: Color.black.opacity(0.22), radius: 12, x: 0, y: 6)
                )
                .padding(.horizontal, 14)
                .padding(.top, 8)
                .transition(.move(edge: .top).combined(with: .opacity))
                .onTapGesture {
                    withAnimation { viewModel.banner = nil }
                }
            }
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
