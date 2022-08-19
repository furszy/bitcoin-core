// Copyright (c) 2021 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <wallet/transaction.h>

#include <wallet/coincontrol.h>
#include <kernel/chain.h>
#include <validation.h>
#include <wallet/receive.h>
#include <wallet/spend.h>
#include <wallet/test/util.h>
#include <wallet/test/wallet_test_fixture.h>

#include <boost/test/unit_test.hpp>

namespace wallet {
BOOST_FIXTURE_TEST_SUITE(wallet_transaction_tests, BasicTestingSetup)

// Test what happens when the wallet receives a txes with the same id and different witness data.
// The following cases are covered:
//   1) tx with segwit data stripped is received, then the same tx with the segwit data arrives.
//      the wallet must update the stored tx, saving the witness data.
BOOST_FIXTURE_TEST_CASE(store_segwit_tx_data, TestChain100Setup)
{
    // Create wallet and generate few more blocks to confirm balance
    std::unique_ptr<CWallet> wallet = CreateSyncedWallet(*m_node.chain, WITH_LOCK(cs_main, return m_node.chainman->ActiveChain()), m_args, coinbaseKey);
    const auto& coinbase_dest_script = GetScriptForDestination(*Assert(wallet->GetNewDestination(OutputType::BECH32, "coinbase")));
    for (int i=0; i<10; i++) {
        const CBlock& block = CreateAndProcessBlock({}, coinbase_dest_script);
        wallet->blockConnected(kernel::MakeBlockInfo(WITH_LOCK(cs_main, return m_node.chainman->ActiveChain().Tip()), &block));
    }
    BOOST_ASSERT(GetBalance(*wallet).m_mine_trusted == COIN * 50 * 10);

    const auto& dest_script = GetScriptForDestination(*Assert(wallet->GetNewDestination(OutputType::BECH32, "")));
    uint256 recv_tx_hash;
    {
        // create the P2WPKH output that will later be spent
        CCoinControl coin_control;
        auto op_tx = Assert(CreateTransaction(*wallet, {{dest_script, 10 * COIN, true}}, 1, coin_control));
        recv_tx_hash = op_tx->tx->GetHash();
        const CBlock& block = CreateAndProcessBlock({CMutableTransaction(*op_tx->tx)}, coinbase_dest_script);
        wallet->blockConnected(kernel::MakeBlockInfo(WITH_LOCK(cs_main, return m_node.chainman->ActiveChain().Tip()), &block));
    }

    {
        // Create the spending tx, strip the witness data and verify that the wallet still accepts it
        CCoinControl coin_control;
        coin_control.m_allow_other_inputs = false;
        coin_control.Select({recv_tx_hash, 0});
        auto op_spend_tx = Assert(CreateTransaction(*wallet, {{dest_script, 10 * COIN, true}}, 1, coin_control));
        BOOST_ASSERT(op_spend_tx->tx->HasWitness());
        const uint256& txid = op_spend_tx->tx->GetHash();

        CMutableTransaction mtx(*op_spend_tx->tx);
        CScriptWitness witness_copy = mtx.vin[0].scriptWitness;
        mtx.vin[0].scriptWitness.SetNull();
        wallet->transactionAddedToMempool(MakeTransactionRef(mtx), /*mempool_sequence=*/0);
        const CWalletTx* wtx_no_witness = WITH_LOCK(wallet->cs_wallet, return wallet->GetWalletTx(txid));
        BOOST_CHECK(wtx_no_witness);
        BOOST_CHECK(wtx_no_witness->GetWitnessHash() == txid);

        // Re-set the witness and verify that the wallet updates the tx witness data by including the tx in a block
        mtx.vin[0].scriptWitness = witness_copy;
        const CBlock& block = CreateAndProcessBlock({mtx}, coinbase_dest_script);
        wallet->blockConnected(kernel::MakeBlockInfo(WITH_LOCK(cs_main, return m_node.chainman->ActiveChain().Tip()), &block));
        const CWalletTx* wtx_with_witness = WITH_LOCK(wallet->cs_wallet, return wallet->GetWalletTx(txid));
        BOOST_CHECK(wtx_with_witness);
        BOOST_CHECK(wtx_with_witness->GetWitnessHash() != txid);

        // Reload the wallet as it would be reloaded from disk and check that the witness data is still there.
        // (flush the previous wallet first)
        wallet->Flush();
        DatabaseOptions options;
        std::unique_ptr<CWallet> wallet_reloaded = std::make_unique<CWallet>(m_node.chain.get(), "", m_args,
                                                                             DuplicateMockDatabase(wallet->GetDatabase(),options));
        BOOST_ASSERT(wallet_reloaded->LoadWallet() == DBErrors::LOAD_OK);
        const CWalletTx* reloaded_wtx_with_witness = WITH_LOCK(wallet->cs_wallet, return wallet_reloaded->GetWalletTx(txid));
        BOOST_CHECK_EQUAL(reloaded_wtx_with_witness->GetWitnessHash(), wtx_with_witness->GetWitnessHash());
    }
}

BOOST_AUTO_TEST_CASE(roundtrip)
{
    for (uint8_t hash = 0; hash < 5; ++hash) {
        for (int index = -2; index < 3; ++index) {
            TxState state = TxStateInterpretSerialized(TxStateUnrecognized{uint256{hash}, index});
            BOOST_CHECK_EQUAL(TxStateSerializedBlockHash(state), uint256{hash});
            BOOST_CHECK_EQUAL(TxStateSerializedIndex(state), index);
        }
    }
}

BOOST_AUTO_TEST_SUITE_END()
} // namespace wallet
