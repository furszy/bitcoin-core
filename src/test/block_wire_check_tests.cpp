// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/block_wire_check.h>

#include <consensus/merkle.h>
#include <consensus/validation.h>
#include <hash.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <script/script.h>
#include <streams.h>
#include <test/util/setup_common.h>
#include <uint256.h>

#include <boost/test/unit_test.hpp>

#include <cstring>
#include <span>
#include <vector>

using node::BlockBodyStatus;
using node::CheckBlockBodyCommitments;
using node::HashTransactionFromWire;

namespace {
//! The block body as it appears on the wire: the transaction count followed by
//! each transaction (with witness).
std::vector<std::byte> SerializeBody(const CBlock& block)
{
    DataStream ss;
    ss << TX_WITH_WITNESS(block.vtx);
    return {ss.begin(), ss.end()};
}

CMutableTransaction MakeCoinbase()
{
    CMutableTransaction cb;
    cb.vin.resize(1);
    cb.vin[0].prevout.SetNull();
    cb.vin[0].scriptSig = CScript() << OP_0 << OP_0;
    cb.vout.resize(1);
    cb.vout[0].nValue = 50 * 100000000LL;
    cb.vout[0].scriptPubKey = CScript() << OP_TRUE;
    return cb;
}

//! Append a BIP141 witness commitment to the block's coinbase, committing to the
//! block's witness root with `reserved` as the coinbase witness reserved value.
void AddWitnessCommitment(CBlock& block, const uint256& reserved)
{
    CMutableTransaction cb{*block.vtx[0]};
    cb.vin[0].scriptWitness.stack.assign(1, std::vector<unsigned char>(reserved.begin(), reserved.end()));
    block.vtx[0] = MakeTransactionRef(cb);

    uint256 commitment = BlockWitnessMerkleRoot(block);
    CHash256().Write(commitment).Write(reserved).Finalize(commitment);

    CScript spk;
    spk.resize(MINIMUM_WITNESS_COMMITMENT);
    spk[0] = OP_RETURN;
    spk[1] = 0x24;
    spk[2] = 0xaa;
    spk[3] = 0x21;
    spk[4] = 0xa9;
    spk[5] = 0xed;
    std::memcpy(&spk[6], commitment.begin(), 32);
    CMutableTransaction cb2{*block.vtx[0]};
    cb2.vout.emplace_back(0, spk);
    block.vtx[0] = MakeTransactionRef(cb2);
}
} // namespace

BOOST_FIXTURE_TEST_SUITE(block_wire_check_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(hash_transaction_from_wire)
{
    const CTransaction tx{MakeCoinbase()};
    DataStream ss;
    ss << TX_WITH_WITNESS(tx);
    const std::vector<std::byte> wire{ss.begin(), ss.end()};

    const auto h = HashTransactionFromWire(wire);
    BOOST_REQUIRE(h.has_value());
    BOOST_CHECK_EQUAL(h->size, wire.size());
    BOOST_CHECK(h->txid == (HashWriter{} << TX_NO_WITNESS(tx)).GetHash());
    BOOST_CHECK(h->wtxid == (HashWriter{} << TX_WITH_WITNESS(tx)).GetHash());
    BOOST_CHECK(!h->has_witness);

    // A truncated transaction cannot be walked.
    BOOST_CHECK(!HashTransactionFromWire(std::span{wire}.first(wire.size() - 1)).has_value());
}

BOOST_AUTO_TEST_CASE(non_witness_block)
{
    CBlock block;
    block.vtx.push_back(MakeTransactionRef(MakeCoinbase()));
    block.hashMerkleRoot = BlockMerkleRoot(block);
    const auto body = SerializeBody(block);

    const auto match = CheckBlockBodyCommitments(block.hashMerkleRoot, body);
    BOOST_CHECK(match.status == BlockBodyStatus::MATCHES);
    BOOST_CHECK(!match.has_witness);

    // A wrong merkle root is a mutation.
    const auto wrong = CheckBlockBodyCommitments(uint256::ONE, body);
    BOOST_CHECK(wrong.status == BlockBodyStatus::MUTATED);

    // A truncated body is malformed.
    const auto trunc = CheckBlockBodyCommitments(block.hashMerkleRoot, std::span{body}.first(body.size() - 1));
    BOOST_CHECK(trunc.status == BlockBodyStatus::MALFORMED);
}

BOOST_AUTO_TEST_CASE(witness_commitment)
{
    CBlock block;
    block.vtx.push_back(MakeTransactionRef(MakeCoinbase()));
    AddWitnessCommitment(block, uint256::ZERO);
    block.hashMerkleRoot = BlockMerkleRoot(block);
    const auto body = SerializeBody(block);

    const auto match = CheckBlockBodyCommitments(block.hashMerkleRoot, body);
    BOOST_CHECK(match.status == BlockBodyStatus::MATCHES);
    BOOST_CHECK(match.has_witness);

    // Changing the coinbase's reserved value breaks the witness commitment
    // without touching any txid: the header merkle root still matches, but the
    // commitment no longer does.
    CBlock tampered = block;
    CMutableTransaction cb{*tampered.vtx[0]};
    cb.vin[0].scriptWitness.stack.assign(1, std::vector<unsigned char>(32, 0x11));
    tampered.vtx[0] = MakeTransactionRef(cb);
    const auto wit = CheckBlockBodyCommitments(block.hashMerkleRoot, SerializeBody(tampered));
    BOOST_CHECK(wit.status == BlockBodyStatus::MUTATED);
    BOOST_CHECK(wit.has_witness);
}

BOOST_AUTO_TEST_SUITE_END()
