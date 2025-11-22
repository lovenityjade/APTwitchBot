#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <set>
#include <list>
#include <map>
#include <ctime>
#include <mutex>
#include <thread>
#include <chrono>

#include <nlohmann/json.hpp>

// apclientpp
#include "apclient.hpp"
#include "apuuid.hpp"

using json = nlohmann::json;

// ------------------------------------------------------------
// Global config & state
// ------------------------------------------------------------

json g_config;
std::mutex g_state_mutex;

struct FetcherState {
    // Room / seed info
    std::string room_name;
    std::string seed;
    std::string server_version;
    std::string generator_version;
    int hint_points = 0;
    int hint_cost_percent = 0;
    int hint_cost_points = 0;

    // Slot / player info
    std::string slot_name;
    std::string game;
    int slot_id = -1;
    int team_id = -1;
    int player_number = -1;
    int team_number = -1;

    // Locations checked
    std::set<int64_t> checked_locations;

    // Items reçus
    struct ItemEvent {
        int64_t index = -1;
        int64_t item = 0;
        int64_t location = 0;
        int player = 0;
        unsigned flags = 0;
        std::time_t timestamp = 0;
    };
    std::vector<ItemEvent> items;

    // Misc data storage / datapackage
    json data_storage = json::object();
};

FetcherState g_state;

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------

static std::string version_to_string(const APClient::Version& v)
{
    return std::to_string(v.ma) + "." +
           std::to_string(v.mi) + "." +
           std::to_string(v.build);
}

void log_to_file(const std::string& msg)
{
    try {
        if (!g_config.contains("paths") || !g_config["paths"].contains("fetcher_log")) {
            return;
        }
        const std::string log_path = g_config["paths"]["fetcher_log"].get<std::string>();

        std::ofstream out(log_path, std::ios::app);
        if (!out) {
            return;
        }

        std::time_t now = std::time(nullptr);
        char buf[64];
        std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&now));

        out << "[" << buf << "] " << msg << '\n';
    }
    catch (...) {
        // Logging must never throw
    }
}

void save_state_to_file()
{
    try {
        if (!g_config.contains("paths") || !g_config["paths"].contains("state_file")) {
            return;
        }
        const std::string state_path = g_config["paths"]["state_file"].get<std::string>();

        json out = json::object();
        {
            std::lock_guard<std::mutex> lock(g_state_mutex);

            // Room/meta
            json room = json::object();
            room["room_name"]          = g_state.room_name;
            room["seed"]               = g_state.seed;
            room["server_version"]     = g_state.server_version;
            room["generator_version"]  = g_state.generator_version;
            room["hint_points"]        = g_state.hint_points;
            room["hint_cost_percent"]  = g_state.hint_cost_percent;
            room["hint_cost_points"]   = g_state.hint_cost_points;

            // Total des locations (si le DataPackage est disponible)
            int total_locations = 0;
            try {
                auto it_dp = g_state.data_storage.find("data_package");
                if (it_dp != g_state.data_storage.end()) {
                    const json& dp = it_dp.value();

                    if (dp.contains("games") && dp["games"].contains(g_state.game)) {
                        const json& game_obj = dp["games"][g_state.game];
                        if (game_obj.contains("locations") && game_obj["locations"].is_object()) {
                            total_locations = static_cast<int>(game_obj["locations"].size());
                        }
                    }
                }
            } catch (const std::exception& e) {
                log_to_file(std::string("[WARN] Failed to compute location_count: ") + e.what());
            }
            room["location_count"] = total_locations;

            out["room"] = room;

            // Slot / me
            json me = json::object();
            me["slot_name"]     = g_state.slot_name;
            me["game"]          = g_state.game;
            me["slot_id"]       = g_state.slot_id;
            me["team_id"]       = g_state.team_id;
            me["player_number"] = g_state.player_number;
            me["team_number"]   = g_state.team_number;
            out["me"] = me;

            // Checked locations
            json checks = json::array();
            for (auto loc : g_state.checked_locations) {
                checks.push_back(loc);
            }
            out["checked_locations"] = checks;

            // Items
            json items = json::array();
            for (const auto& it : g_state.items) {
                json ji;
                ji["index"]    = it.index;
                ji["item"]     = it.item;
                ji["location"] = it.location;
                ji["player"]   = it.player;
                ji["flags"]    = it.flags;
                ji["time"]     = it.timestamp;
                items.push_back(ji);
            }
            out["items"] = items;
            
            // Data storage / datapackage snapshot
            out["data_storage"] = g_state.data_storage;
        }

        // Copy some config bits that are useful for the bot
        if (g_config.contains("archipelago")) {
            out["archipelago"] = g_config["archipelago"];
        }

        std::ofstream state_file(state_path, std::ios::trunc);
        if (!state_file) {
            log_to_file("[ERROR] Unable to open state file for writing: " + state_path);
            return;
        }
        state_file << out.dump(2);
        state_file.close();
    }
    catch (const std::exception& e) {
        log_to_file(std::string("[ERROR] save_state_to_file: ") + e.what());
    }
    catch (...) {
        log_to_file("[ERROR] save_state_to_file: unknown exception");
    }
}

// ------------------------------------------------------------
// Main
// ------------------------------------------------------------

int main()
{
    try {
        // ----------------------------
        // Load config/config.json
        // ----------------------------
        {
            std::ifstream cfg("config/config.json");
            if (!cfg) {
                // si on lance depuis build/, on remonte d'un cran
                cfg.open("../config/config.json");
            }
            if (!cfg) {
                std::cerr << "[FETCHER] Unable to open config/config.json" << std::endl;
                return 1;
            }
            cfg >> g_config;
        }

        if (!g_config.contains("archipelago")) {
            std::cerr << "[FETCHER] Missing 'archipelago' section in config" << std::endl;
            return 1;
        }

        const json& arch = g_config["archipelago"];

        const std::string host      = arch.value("host", std::string("localhost"));
        const int         port      = arch.value("port", 38281);
        const std::string game      = arch.value("game", std::string("Unknown Game"));
        const std::string slot_name = arch.value("slot_name", std::string("Player"));
        const std::string password  = arch.value("password", std::string(""));
        const int items_handling    = arch.value("items_handling", 7); // receive all items by default

        const std::string uri = host + ":" + std::to_string(port);

        // UUID: if we have a file path configured, use it, otherwise use a default in data/
        std::string uuid_file = "data/ap_uuid.txt";
        if (g_config.contains("paths") && g_config["paths"].contains("uuid_file")) {
            uuid_file = g_config["paths"]["uuid_file"].get<std::string>();
        }

        std::string uuid;
        try {
            uuid = ap_get_uuid(uuid_file, host);
        }
        catch (...) {
            uuid.clear(); // empty uuid is allowed by apclientpp
        }

        log_to_file("[AP] Starting fetcher");
        log_to_file("[AP] Connecting to " + uri + " game=" + game + " slot=" + slot_name);

        // ------------------------------------------------
        // Instantiate APClient
        // ------------------------------------------------
        APClient client(uuid, game, uri);

        // ------------------------------------------------
        // Handlers
        // ------------------------------------------------

        // Socket-level events
        client.set_socket_connected_handler([&]() {
            log_to_file("[AP] Socket connected");
        });

        client.set_socket_error_handler([&](const std::string& err) {
            log_to_file(std::string("[AP] Socket error: ") + err);
        });

        client.set_socket_disconnected_handler([&]() {
            log_to_file("[AP] Socket disconnected");
        });

        // RoomInfo: called once we know the room, seed, versions, etc.
        client.set_room_info_handler([&]() {
            log_to_file("[AP] RoomInfo received");

            {   
                std::lock_guard<std::mutex> lock(g_state_mutex);
                g_state.seed              = client.get_seed();
                g_state.server_version    = version_to_string(client.get_server_version());
                g_state.generator_version = version_to_string(client.get_generator_version());
                g_state.hint_points       = client.get_hint_points();
                g_state.hint_cost_percent = client.get_hint_cost_percent();
                // room_name non exposé directement, on pourra l’ajouter plus tard via datapackage
            }

            // IMPORTANT : on sauvegarde en dehors du lock
            save_state_to_file();

            try {
                std::list<std::string> include{ game };
                if (!client.GetDataPackage(include)) {
                    log_to_file("[AP] GetDataPackage() returned false");
                } else {
                    log_to_file("[AP] GetDataPackage() requested");
                }
            } catch (const std::exception& e) {
                log_to_file(std::string("[ERROR] GetDataPackage: ") + e.what());
            }

            // Build tags from config if present
            std::list<std::string> tags;
            if (arch.contains("tags") && arch["tags"].is_array()) {
                for (const auto& t : arch["tags"]) {
                    tags.push_back(t.get<std::string>());
                }
            }

            // Connect the slot as soon as we have RoomInfo
            bool ok = client.ConnectSlot(slot_name, password, items_handling, tags, APCLIENTPP_VERSION_INITIALIZER);
            if (!ok) {
                log_to_file("[AP] ConnectSlot() returned false (state not ready yet?)");
            } else {
                log_to_file("[AP] ConnectSlot() sent");
            }
        });

        // SlotConnected: we now know who we are (slot/team/etc.)
        client.set_slot_connected_handler([&](const json& slot_data) {
            log_to_file("[AP] SlotConnected");

            {
                std::lock_guard<std::mutex> lock(g_state_mutex);

                // Infos de base sur le slot
                g_state.slot_name     = client.get_slot();
                g_state.player_number = client.get_player_number();
                g_state.team_number   = client.get_team_number();

                if (slot_data.contains("game")) {
                    g_state.game = slot_data["game"].get<std::string>();
                } else {
                    g_state.game = game;
                }

                if (slot_data.contains("slot")) {
                    g_state.slot_id = slot_data["slot"].get<int>();
                }
                if (slot_data.contains("team")) {
                    g_state.team_id = slot_data["team"].get<int>();
                }

                // On garde le JSON brut pour le bot si besoin
                g_state.data_storage["slot_data"] = slot_data;
            }

            // Sauvegarde en dehors du lock
            save_state_to_file();
        });

        client.set_slot_disconnected_handler([&]() {
            log_to_file("[AP] SlotDisconnected");
        });

        // Data package: texts, item/location names, etc.
        client.set_data_package_changed_handler([&](const json& dp) {
            log_to_file("[AP] DataPackageChanged");
            {
                std::lock_guard<std::mutex> lock(g_state_mutex);
                g_state.data_storage["data_package"] = dp;
            }
            save_state_to_file();
        });

        // Location checks (our local checks, or sync)
        client.set_location_checked_handler([&](const std::list<int64_t>& locations) {
            std::lock_guard<std::mutex> lock(g_state_mutex);
            for (auto loc : locations) {
                g_state.checked_locations.insert(loc);
            }
            log_to_file("[AP] LocationChecked: +" + std::to_string(locations.size()));
            // Le flush disque se fait dans la boucle principale pour éviter de spammer.
        });

        // ItemsReceived: all items that go to this slot
        client.set_items_received_handler([&](const std::list<APClient::NetworkItem>& items) {
            std::time_t now = std::time(nullptr);

            {
                std::lock_guard<std::mutex> lock(g_state_mutex);
                for (const auto& it : items) {
                    FetcherState::ItemEvent evt;
                    evt.index     = it.index;
                    evt.item      = it.item;
                    evt.location  = it.location;
                    evt.player    = it.player;
                    evt.flags     = it.flags;
                    evt.timestamp = now;
                    g_state.items.push_back(evt);
                }
            }

            log_to_file("[AP] ReceivedItems: +" + std::to_string(items.size()));
            // On laisse la boucle principale gérer la fréquence d'écriture sur disque.
        });

        // Chat / print JSON: on log tout, le bot pourra parser si besoin
        client.set_print_json_handler([&](const json& msg) {
            log_to_file(std::string("[AP] PrintJSON: ") + msg.dump());
        });

        // Retrieved handler (DataStorage Get replies) – gardé pour plus tard
        client.set_retrieved_handler([&](const std::map<std::string, json>& map) {
            std::lock_guard<std::mutex> lock(g_state_mutex);
            for (const auto& kv : map) {
                g_state.data_storage["retrieved"][kv.first] = kv.second;
            }
            save_state_to_file();
        });

        // ------------------------------------------------
        // Main poll loop
        // ------------------------------------------------
        int flush_interval = 2;
        if (g_config.contains("fetcher") && g_config["fetcher"].contains("flush_interval")) {
            try {
                flush_interval = g_config["fetcher"]["flush_interval"].get<int>();
            } catch (...) {
                flush_interval = 2;
            }
        }

        using clock = std::chrono::steady_clock;
        auto last_flush = clock::now();

        while (true) {
            client.poll();

            auto now = clock::now();
            if (std::chrono::duration_cast<std::chrono::seconds>(now - last_flush).count() >= flush_interval) {
                save_state_to_file();
                last_flush = now;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }

        return 0; // jamais atteint
    }
    catch (const std::exception& e) {
        std::cerr << "[FETCHER] Exception: " << e.what() << std::endl;
        log_to_file(std::string("[ERROR] ") + e.what());
        return 1;
    }
    catch (...) {
        std::cerr << "[FETCHER] Unknown exception" << std::endl;
        log_to_file("[ERROR] Unknown exception in main()");
        return 1;
    }
}
