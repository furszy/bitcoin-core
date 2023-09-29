// Copyright (c) 2023 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include <bench/bench.h>
#include <interfaces/chain.h>
#include <node/context.h>
#include <test/util/mining.h>
#include <test/util/setup_common.h>
#include <wallet/test/util.h>
#include <wallet/context.h>
#include <wallet/receive.h>
#include <wallet/wallet.h>

#include <optional>

#ifdef USE_BDB // only enable benchmark when bdb is enabled

namespace wallet{

static void WalletMigration(benchmark::Bench& bench)
{
    const auto test_setup = MakeNoLogFileContext<TestingSetup>();

    WalletContext context;
    context.args = &test_setup->m_args;
    context.chain = test_setup->m_node.chain.get();

    // Number of wallets to migrate
    int NUM_WALLETS = 1;
    // Number of imported watch only addresses
    int NUM_WATCH_ONLY_ADDR = 20;

    // Setup legacy wallets
    for (int i = 0; i < NUM_WALLETS; ++i) {
        DatabaseOptions options;
        DatabaseStatus status;
        bilingual_str error;
        std::string filename = strprintf("legacy_%d", i);
        auto database = MakeWalletDatabase(test_setup->m_path_root / filename.c_str(), options, status, error);
        uint64_t create_flags = 0;
        auto wallet = TestLoadWallet(std::move(database), context, create_flags);

        // Add watch-only addresses
        std::vector<CScript> scripts_watch_only;
        for (int w = 0; w < NUM_WATCH_ONLY_ADDR; ++w) {
            CKey key;
            key.MakeNewKey(true);
            LOCK(wallet->cs_wallet);
            const CScript& script = scripts_watch_only.emplace_back(GetScriptForDestination(GetDestinationForKey(key.GetPubKey(), OutputType::LEGACY)));
            bool res = wallet->ImportScriptPubKeys(strprintf("watch_%d", w), {script},
                                        /*have_solving_data=*/false, /*apply_label=*/true, /*timestamp=*/1);
            assert(res);
        }

        // Generate transactions and local addresses
        for (int j = 0; j < 600; ++j) {
            CMutableTransaction mtx;
            mtx.vout.push_back(CTxOut(COIN, GetScriptForDestination(*Assert(wallet->GetNewDestination(OutputType::BECH32, strprintf("bench_%d", j))))));
            mtx.vout.push_back(CTxOut(COIN, GetScriptForDestination(*Assert(wallet->GetNewDestination(OutputType::LEGACY, strprintf("legacy_%d", j))))));
            mtx.vout.push_back(CTxOut(COIN, scripts_watch_only.at(j % NUM_WATCH_ONLY_ADDR)));
            mtx.vin.resize(2);
            wallet->AddToWallet(MakeTransactionRef(mtx), TxStateInactive{}, /*update_wtx=*/nullptr, /*fFlushOnClose=*/false, /*rescanning_old_block=*/true);
        }

        // Unload so the migration process loads it
        TestUnloadWallet(std::move(wallet));
    }

    int wallet_num = 0;
    bench.epochs(NUM_WALLETS).run([&] {
        std::string filename = strprintf("legacy_%d", wallet_num);
        util::Result<MigrationResult> res = MigrateLegacyToDescriptor(test_setup->m_path_root / filename.c_str(), "", context);
        assert(res);
        assert(res->wallet);
        assert(res->watchonly_wallet);
        wallet_num++;
    });
}

BENCHMARK(WalletMigration, benchmark::PriorityLevel::LOW);

} // namespace wallet

#endif // end USE_BDB
