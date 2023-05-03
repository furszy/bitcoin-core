// Copyright (c) 2012-2021 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <test/util/setup_common.h>
#include <clientversion.h>
#include <streams.h>
#include <uint256.h>
#include <wallet/test/util.h>
#include <wallet/walletdb.h>

#include <boost/test/unit_test.hpp>

namespace wallet {
BOOST_FIXTURE_TEST_SUITE(walletdb_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(walletdb_readkeyvalue)
{
    /**
     * When ReadKeyValue() reads from either a "key" or "wkey" it first reads the CDataStream steam into a
     * CPrivKey or CWalletKey respectively and then reads a hash of the pubkey and privkey into a uint256.
     * Wallets from 0.8 or before do not store the pubkey/privkey hash, trying to read the hash from old
     * wallets throws an exception, for backwards compatibility this read is wrapped in a try block to
     * silently fail. The test here makes sure the type of exception thrown from CDataStream::read()
     * matches the type we expect, otherwise we need to update the "key"/"wkey" exception type caught.
     */
    CDataStream ssValue(SER_DISK, CLIENT_VERSION);
    uint256 dummy;
    BOOST_CHECK_THROW(ssValue >> dummy, std::ios_base::failure);
}

BOOST_AUTO_TEST_CASE(mock_db_erase_prefix)
{
    // Test mock db erase prefix function
    std::unique_ptr<WalletDatabase> db = CreateMockableWalletDatabase();
    WalletBatch batch(*db);

    CTxDestination dest1 = PKHash();
    CTxDestination dest2 = ScriptHash();

    BOOST_CHECK(batch.WriteAddressPreviouslySpent(dest1, true));
    BOOST_CHECK(batch.WriteAddressPreviouslySpent(dest2, true));
    BOOST_CHECK(batch.WriteAddressReceiveRequest(dest1, "0", "val_rr00"));

    // Check that we have the data stored
    MockableDatabase* mock_db = dynamic_cast<MockableDatabase*>(db.get());
    BOOST_CHECK_EQUAL(mock_db->m_records.size(), 3);

    // Erase dest1 data
    BOOST_CHECK(batch.EraseAddressData(dest1));
    BOOST_CHECK_EQUAL(mock_db->m_records.size(), 1);
}

BOOST_AUTO_TEST_SUITE_END()
} // namespace wallet
