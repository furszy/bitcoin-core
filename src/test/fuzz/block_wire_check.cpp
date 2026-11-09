// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <consensus/merkle.h>
#include <consensus/validation.h>
#include <hash.h>
#include <node/block_wire_check.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <script/script.h>
#include <streams.h>
#include <test/fuzz/FuzzedDataProvider.h>
#include <test/fuzz/fuzz.h>
#include <uint256.h>

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <ios>
#include <span>
#include <vector>

namespace {
uint256 ConsumeUInt256(FuzzedDataProvider& fdp)
{
    auto b = fdp.ConsumeBytes<unsigned char>(32);
    b.resize(32);
    uint256 v;
    std::memcpy(v.begin(), b.data(), 32);
    return v;
}

CScript ConsumeScript(FuzzedDataProvider& fdp)
{
    const auto b = fdp.ConsumeBytes<unsigned char>(fdp.ConsumeIntegralInRange<size_t>(0, 40));
    return CScript{b.begin(), b.end()};
}
} // namespace

// Differential test: HashTransactionFromWire() walks a transaction's wire bytes
// without materializing it, and must return exactly the txid/wtxid/size a real
// CTransaction would -- for every input the normal deserializer accepts. It
// must also never over-read on arbitrary bytes.
FUZZ_TARGET(block_wire_check_tx)
{
    // On arbitrary bytes the walker must not over-read, and if it accepts a
    // prefix as a transaction then the deserializer must accept exactly that
    // prefix and agree on the hashes -- neither may be more lenient than the
    // other. Coinbase extraction (which reads the outputs and the witness) is
    // exercised here too.
    {
        node::CoinbaseWitnessData cb;
        if (const auto h = node::HashTransactionFromWire(std::as_bytes(std::span{buffer}), &cb)) {
            assert(h->size <= buffer.size());
            DataStream ds{buffer.first(h->size)};
            CMutableTransaction mtx;
            bool accepted = true;
            try {
                ds >> TX_WITH_WITNESS(mtx);
            } catch (const std::ios_base::failure&) {
                accepted = false;
            }
            assert(accepted && ds.empty()); // the walker's span is exactly one transaction
            const CTransaction tx{mtx};
            assert(h->txid == (HashWriter{} << TX_NO_WITNESS(tx)).GetHash());
            assert(h->wtxid == (HashWriter{} << TX_WITH_WITNESS(tx)).GetHash());
        }
    }

    // Conversely, every transaction the deserializer accepts, the walker
    // accepts and agrees on, over its canonical re-serialization.
    DataStream ds{buffer};
    CMutableTransaction mtx;
    try {
        ds >> TX_WITH_WITNESS(mtx);
    } catch (const std::ios_base::failure&) {
        return;
    }
    const CTransaction tx{mtx};

    DataStream reser;
    reser << TX_WITH_WITNESS(tx);
    const std::vector<std::byte> wire{reser.begin(), reser.end()};

    const auto got = node::HashTransactionFromWire(wire);
    assert(got.has_value());
    assert(got->size == wire.size());
    assert(got->txid == (HashWriter{} << TX_NO_WITNESS(tx)).GetHash());
    assert(got->wtxid == (HashWriter{} << TX_WITH_WITNESS(tx)).GetHash());
}

// Differential test: BlockBodyMatchesCommitments() must accept a block's body
// exactly when CheckBlock's merkle-root check and CheckWitnessMalleation (with
// segwit active) would, over constructed blocks that sometimes carry a real
// witness commitment and sometimes a corrupted merkle root.
FUZZ_TARGET(block_wire_check_block)
{
    FuzzedDataProvider fdp{buffer.data(), buffer.size()};

    const int ntx = fdp.ConsumeIntegralInRange<int>(1, 6);
    std::vector<CTransactionRef> vtx;
    vtx.reserve(ntx);
    for (int i = 0; i < ntx; ++i) {
        CMutableTransaction mtx;
        mtx.version = fdp.ConsumeIntegral<uint32_t>();
        mtx.nLockTime = fdp.ConsumeIntegral<uint32_t>();
        const int nin = fdp.ConsumeIntegralInRange<int>(1, 3);
        for (int k = 0; k < nin; ++k) {
            CTxIn in;
            in.prevout.n = fdp.ConsumeIntegral<uint32_t>();
            in.scriptSig = ConsumeScript(fdp);
            in.nSequence = fdp.ConsumeIntegral<uint32_t>();
            if (fdp.ConsumeBool()) {
                const int items = fdp.ConsumeIntegralInRange<int>(0, 3);
                for (int w = 0; w < items; ++w) {
                    in.scriptWitness.stack.push_back(fdp.ConsumeBytes<unsigned char>(fdp.ConsumeIntegralInRange<size_t>(0, 34)));
                }
            }
            mtx.vin.push_back(std::move(in));
        }
        const int nout = fdp.ConsumeIntegralInRange<int>(0, 3);
        for (int k = 0; k < nout; ++k) {
            mtx.vout.emplace_back(fdp.ConsumeIntegral<int64_t>(), ConsumeScript(fdp));
        }
        vtx.push_back(MakeTransactionRef(std::move(mtx)));
    }

    // Optionally give the coinbase a valid witness commitment.
    if (fdp.ConsumeBool()) {
        const uint256 reserved = ConsumeUInt256(fdp);
        CMutableTransaction cb{*vtx[0]};
        cb.vin[0].scriptWitness.stack.assign(1, std::vector<unsigned char>(reserved.begin(), reserved.end()));
        vtx[0] = MakeTransactionRef(std::move(cb));

        CBlock tmp;
        tmp.vtx = vtx;
        uint256 commitment = BlockWitnessMerkleRoot(tmp);
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
        CMutableTransaction cb2{*vtx[0]};
        cb2.vout.emplace_back(int64_t{0}, spk);
        vtx[0] = MakeTransactionRef(std::move(cb2));
    }

    CBlock block;
    block.vtx = vtx;
    // A correct merkle root, or (sometimes) a corrupted one, to exercise both
    // acceptance and rejection.
    block.hashMerkleRoot = fdp.ConsumeBool() ? BlockMerkleRoot(block) : ConsumeUInt256(fdp);

    // Serialize the body (transaction count + transactions) and wire-check it.
    DataStream bodystream;
    bodystream << TX_WITH_WITNESS(block.vtx);
    const std::vector<std::byte> body{bodystream.begin(), bodystream.end()};
    const node::BlockBodyCheck result = node::CheckBlockBodyCommitments(block.hashMerkleRoot, body);
    // A well-formed constructed body is never malformed to the walker, and its
    // witness flag matches the materialized block.
    assert(result.status != node::BlockBodyStatus::MALFORMED);
    bool any_witness = false;
    for (const auto& tx : block.vtx) {
        if (tx->HasWitness()) any_witness = true;
    }
    assert(result.has_witness == any_witness);
    const bool wire_ok = result.status == node::BlockBodyStatus::MATCHES;

    // Reference: CheckBlock's merkle-root check + CheckWitnessMalleation.
    bool mutated{false};
    bool ref_ok = BlockMerkleRoot(block, &mutated) == block.hashMerkleRoot && !mutated;
    if (ref_ok) {
        const int commitpos = GetWitnessCommitmentIndex(block);
        if (commitpos != NO_WITNESS_COMMITMENT) {
            const auto& stack = block.vtx[0]->vin[0].scriptWitness.stack;
            if (stack.size() != 1 || stack[0].size() != 32) {
                ref_ok = false;
            } else {
                uint256 hw = BlockWitnessMerkleRoot(block);
                CHash256().Write(hw).Write(stack[0]).Finalize(hw);
                ref_ok = std::memcmp(hw.begin(), &block.vtx[0]->vout[commitpos].scriptPubKey[6], 32) == 0;
            }
        } else {
            for (const auto& tx : block.vtx) {
                if (tx->HasWitness()) {
                    ref_ok = false;
                    break;
                }
            }
        }
    }

    assert(wire_ok == ref_ok);
}
