// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chainparams.h>
#include <index/txospenderindex.h>
#include <test/util/setup_common.h>
#include <util/time.h>
#include <validation.h>

#include <boost/test/unit_test.hpp>

BOOST_AUTO_TEST_SUITE(txospenderindex_tests)

BOOST_FIXTURE_TEST_CASE(txospenderindex_initial_sync, TestChain100Setup)
{
    // Setup phase:
    // Mine blocks for coinbase maturity, so we can spend some coinbase outputs in the test.
    const CScript& coinbase_script = m_coinbase_txns[0]->vout[0].scriptPubKey;
    for (int i = 0; i < 50; i++) {
        CreateAndProcessBlock({}, coinbase_script);
    }

    // Spend 10 outputs
    std::vector<COutPoint> spent(10);
    std::vector<CMutableTransaction> spender(spent.size());
    for (size_t i = 0; i < spent.size(); i++) {
        // Outpoint
        auto output = m_coinbase_txns[i];
        spent[i] = COutPoint(output->GetHash(), 0);

        // Spending tx
        spender[i].version = 1;
        spender[i].vin.resize(1);
        spender[i].vin[0].prevout.hash = spent[i].hash;
        spender[i].vin[0].prevout.n = spent[i].n;
        spender[i].vout.resize(1);
        spender[i].vout[0].nValue = output->GetValueOut();
        spender[i].vout[0].scriptPubKey = coinbase_script;

        // Sign
        std::vector<unsigned char> vchSig;
        const uint256 hash = SignatureHash(coinbase_script, spender[i], 0, SIGHASH_ALL, 0, SigVersion::BASE);
        coinbaseKey.Sign(hash, vchSig);
        vchSig.push_back((unsigned char)SIGHASH_ALL);
        spender[i].vin[0].scriptSig << vchSig;
    }

    CBlock block = CreateAndProcessBlock(spender, coinbase_script);
    m_node.validation_signals->SyncWithValidationInterfaceQueue();
    uint256 tip_hash = block.GetHash(); // Ensure block has been processed
    BOOST_CHECK_EQUAL(WITH_LOCK(::cs_main, return m_node.chainman->ActiveTip()->GetBlockHash()), tip_hash);

    // Now we concluded the setup phase, run index
    TxoSpenderIndex txospenderindex(interfaces::MakeChain(m_node), 1 << 20, true);
    BOOST_REQUIRE(txospenderindex.Init());
    BOOST_CHECK(!txospenderindex.BlockUntilSyncedToCurrentChain());

    // Transaction should not be found in the index before it is synced.
    for (const auto& outpoint : spent) {
        BOOST_CHECK(!txospenderindex.FindSpender(outpoint).value());
    }

    txospenderindex.Sync();
    BOOST_CHECK_EQUAL(txospenderindex.GetSummary().best_block_hash, tip_hash);

    for (size_t i = 0; i < spent.size(); i++) {
        const auto tx_spender{txospenderindex.FindSpender(spent[i])};
        BOOST_REQUIRE(tx_spender.has_value());
        BOOST_REQUIRE(tx_spender->has_value());
        BOOST_CHECK_EQUAL((*tx_spender)->tx->GetHash(), spender[i].GetHash());
        BOOST_CHECK_EQUAL((*tx_spender)->block_hash, block.GetHash());
    }

    txospenderindex.Stop();
}

BOOST_AUTO_TEST_SUITE_END()
