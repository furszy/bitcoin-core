// Copyright (c) 2020-2021 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <key.h>
#include <script/standard.h>
#include <test/util/setup_common.h>
#include <wallet/scriptpubkeyman.h>
#include <wallet/test/util.h>
#include <wallet/wallet.h>

#include <boost/test/unit_test.hpp>

namespace wallet {
BOOST_FIXTURE_TEST_SUITE(scriptpubkeyman_tests, BasicTestingSetup)

// Test LegacyScriptPubKeyMan::CanProvide behavior, making sure it returns true
// for recognized scripts even when keys may not be available for signing.
BOOST_AUTO_TEST_CASE(CanProvide)
{
    // Set up wallet and keyman variables.
    CWallet wallet(m_node.chain.get(), "", CreateDummyWalletDatabase());
    LegacyScriptPubKeyMan& keyman = *wallet.GetOrCreateLegacyScriptPubKeyMan();

    // Make a 1 of 2 multisig script
    std::vector<CKey> keys(2);
    std::vector<CPubKey> pubkeys;
    for (CKey& key : keys) {
        key.MakeNewKey(true);
        pubkeys.emplace_back(key.GetPubKey());
    }
    CScript multisig_script = GetScriptForMultisig(1, pubkeys);
    CScript p2sh_script = GetScriptForDestination(ScriptHash(multisig_script));
    SignatureData data;

    // Verify the p2sh(multisig) script is not recognized until the multisig
    // script is added to the keystore to make it solvable
    BOOST_CHECK(!keyman.CanProvide(p2sh_script, data));
    keyman.AddCScript(multisig_script);
    BOOST_CHECK(keyman.CanProvide(p2sh_script, data));
}

BOOST_AUTO_TEST_CASE(wallet_register_spkm_signals_test)
{
    // Tests that the wallet is registers to the spkm events
    CWallet wallet(m_node.chain.get(), "", CreateDummyWalletDatabase());
    wallet.m_keypool_size = 1;

    // Register to events
    int events_count{0};
    wallet.NotifyCanGetAddressesChanged.connect([&](){
        events_count++;
    });

    wallet.SetMinVersion(FEATURE_LATEST);
    wallet.SetWalletFlag(WALLET_FLAG_DESCRIPTORS);
    LOCK(wallet.cs_wallet);
    wallet.SetupDescriptorScriptPubKeyMans();

    // For each of the created spkm (internal, external), we should have received 1 event
    int expected_events_count = 2 * OUTPUT_TYPES.size();
    BOOST_CHECK_EQUAL(expected_events_count, events_count);
    events_count = 0;

    // Now import a new descriptor
    import_descriptor(wallet, "wpkh(xprv9s21ZrQH143K2LE7W4Xf3jATf9jECxSb7wj91ZnmY4qEJrS66Qru9RFqq8xbkgT32ya6HqYJweFdJUEDf5Q6JFV7jMiUws7kQfe6Tv4RbfN/0h/0h/*h)",
                      /*range_start=*/0, /*range_end=*/1, /*next_index=*/0);
    // After the import TopUp, 'NotifyCanGetAddressesChanged' should be triggered.
    BOOST_CHECK_EQUAL(1, events_count);
}

BOOST_AUTO_TEST_SUITE_END()
} // namespace wallet
