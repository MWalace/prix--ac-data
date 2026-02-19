import SwiftUI

struct Catalog: Decodable {
    let lastUpdated: String
    let sources: [String]
    let categories: [Category]
}

struct Category: Identifiable, Decodable {
    let id: String
    let name: String
    let items: [Product]
}

struct Product: Identifiable, Decodable {
    let id: String
    let name: String
    let price: String?
    let colorHex: String?
    let appleCare: AppleCarePricing?

    var color: Color {
        Color(hex: colorHex) ?? .accentColor
    }
}

struct AppleCarePricing: Decodable {
    let standardOneTime: String
    let standardMonthly: String
    let theftOneTime: String?
    let theftMonthly: String?
}

@MainActor
final class CatalogViewModel: ObservableObject {
    @Published var catalog: Catalog
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    @Published var lastSync: String?

    init() {
        if let bundledCatalog = Catalog.loadFromBundle() {
            catalog = bundledCatalog
        } else {
            catalog = Catalog.empty
            errorMessage = "Fichier JSON introuvable dans l’app."
        }
    }

    func refresh(from urlString: String) async {
        let trimmedURL = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmedURL) else {
            errorMessage = "URL JSON invalide."
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let decoded = try JSONDecoder().decode(Catalog.self, from: data)
            catalog = decoded
            errorMessage = nil
            lastSync = DateFormatter.shortTimestamp.string(from: Date())
        } catch {
            errorMessage = "Mise à jour impossible. Vérifie l’URL ou le format JSON."
        }
    }
}

struct ContentView: View {
    @StateObject private var viewModel: CatalogViewModel = CatalogViewModel()
    @AppStorage("catalogURL") private var catalogURLString: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("AppleCare+ – Catalogue France")
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                Text("Liste des produits Apple vendus actuellement + tarifs AppleCare+ quand disponibles.")
                    .font(.system(size: 12, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                TextField("URL JSON", text: $catalogURLString)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 420)

                Button {
                    Task { await viewModel.refresh(from: catalogURLString) }
                } label: {
                    if viewModel.isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("Mettre à jour")
                    }
                }
                .disabled(catalogURLString.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)

                if let lastSync = viewModel.lastSync {
                    Text("Dernière synchro : \(lastSync)")
                        .font(.system(size: 11, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                Text("Données : \(viewModel.catalog.lastUpdated)")
                    .font(.system(size: 11, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.system(size: 12, weight: .regular, design: .rounded))
                    .foregroundStyle(.red)
            }

            TabView {
                ForEach(viewModel.catalog.categories) { category in
                    CategoryView(category: category)
                        .tabItem { Text(category.name) }
                }
            }

            Divider()

            SourcesView(sources: viewModel.catalog.sources)
        }
        .padding(20)
    }
}

struct CategoryView: View {
    let category: Category

    private var hasAppleCare: Bool {
        category.items.contains { $0.appleCare != nil }
    }

    var body: some View {
        if #available(macOS 12.0, *) {
            Table(category.items) {
                TableColumn("Produit") { item in
                    ProductBadge(name: item.name, color: item.color)
                }
                .width(min: 160, ideal: 220)

                TableColumn("Prix") { item in
                    Text(item.price ?? "—")
                        .font(.system(size: 12, weight: .semibold))
                }
                .width(min: 120, ideal: 140)

                if hasAppleCare {
                    TableColumn("AC+ 2 ans") { item in
                        Text(item.appleCare?.standardOneTime ?? "—")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .width(min: 90, ideal: 110)

                    TableColumn("AC+ mensuel") { item in
                        Text(item.appleCare?.standardMonthly ?? "—")
                            .font(.system(size: 12))
                    }
                    .width(min: 110, ideal: 130)

                    TableColumn("Perte/Vol 2 ans") { item in
                        Text(item.appleCare?.theftOneTime ?? "—")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .width(min: 110, ideal: 130)

                    TableColumn("Perte/Vol mensuel") { item in
                        Text(item.appleCare?.theftMonthly ?? "—")
                            .font(.system(size: 12))
                    }
                    .width(min: 130, ideal: 150)
                }
            }
            .frame(minHeight: 320)
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(category.items) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                ProductBadge(name: item.name, color: item.color)
                                if let price = item.price {
                                    Text(price)
                                        .font(.system(size: 12, weight: .semibold))
                                }
                            }

                            if hasAppleCare {
                                HStack(spacing: 16) {
                                    PriceCell(title: "AC+ 2 ans", value: item.appleCare?.standardOneTime)
                                    PriceCell(title: "AC+ mensuel", value: item.appleCare?.standardMonthly)
                                    PriceCell(title: "Perte/Vol 2 ans", value: item.appleCare?.theftOneTime)
                                    PriceCell(title: "Perte/Vol mensuel", value: item.appleCare?.theftMonthly)
                                }
                            }
                        }
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(item.color.opacity(0.12))
                        )
                    }
                }
            }
        }
    }
}

struct ProductBadge: View {
    let name: String
    let color: Color

    var body: some View {
        Text(name)
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(color.opacity(0.15))
            )
    }
}

struct PriceCell: View {
    let title: String
    let value: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value ?? "—")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
        }
    }
}

struct SourcesView: View {
    let sources: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Sources officielles")
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            ForEach(sources, id: \.self) { source in
                if let url = URL(string: source) {
                    Link(sourceLabel(from: url), destination: url)
                        .font(.system(size: 11, weight: .regular, design: .rounded))
                }
            }
        }
    }

    private func sourceLabel(from url: URL) -> String {
        let host = url.host ?? "apple.com"
        let path = url.path.isEmpty ? "/" : url.path
        return "\(host)\(path)"
    }
}

extension Catalog {
    static let empty = Catalog(lastUpdated: "—", sources: [], categories: [])

    static func loadFromBundle() -> Catalog? {
        guard let url = Bundle.main.url(forResource: "price-catalog", withExtension: "json") else {
            return nil
        }

        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode(Catalog.self, from: data)
        } catch {
            return nil
        }
    }
}

extension DateFormatter {
    static let shortTimestamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        return formatter
    }()
}

extension Color {
    init?(hex: String?) {
        guard let hex = hex?.trimmingCharacters(in: CharacterSet.alphanumerics.inverted),
              hex.count == 6,
              let value = UInt64(hex, radix: 16) else {
            return nil
        }

        let red = Double((value & 0xFF0000) >> 16) / 255.0
        let green = Double((value & 0x00FF00) >> 8) / 255.0
        let blue = Double(value & 0x0000FF) / 255.0
        self.init(red: red, green: green, blue: blue)
    }
}
