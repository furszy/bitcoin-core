// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/block_wire_check.h>

#include <consensus/merkle.h>
#include <consensus/validation.h>
#include <hash.h>
#include <serialize.h>
#include <span.h>
#include <streams.h>
#include <uint256.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <ios>
#include <optional>
#include <span>
#include <vector>

namespace node {
namespace {
// Skip one length-prefixed byte string (a script or a witness item). The length
// is range-checked by ReadCompactSize and ignore() throws past the end, so a
// malformed length cannot over-read.
void SkipLengthPrefixed(SpanReader& r) { r.ignore(ReadCompactSize(r)); }

// Skip `n` transaction inputs (prevout, scriptSig, sequence) with no witnesses.
void SkipInputs(SpanReader& r, uint64_t n)
{
    for (uint64_t i = 0; i < n; ++i) {
        r.ignore(36);           // COutPoint: txid (32) + index (4)
        SkipLengthPrefixed(r);  // scriptSig
        r.ignore(4);            // nSequence
    }
}

// Return the 32-byte witness commitment carried by a scriptPubKey, if it is a
// witness-commitment output (OP_RETURN, length byte 0x24, header 0xaa21a9ed,
// then the commitment). Mirrors GetWitnessCommitmentIndex().
std::optional<uint256> WitnessCommitment(std::span<const std::byte> spk)
{
    static constexpr std::array<unsigned char, 6> kPrefix{0x6a /* OP_RETURN */, 0x24, 0xaa, 0x21, 0xa9, 0xed};
    if (spk.size() < MINIMUM_WITNESS_COMMITMENT) return std::nullopt;
    for (size_t i = 0; i < kPrefix.size(); ++i) {
        if (std::to_integer<unsigned char>(spk[i]) != kPrefix[i]) return std::nullopt;
    }
    return uint256{MakeUCharSpan(spk.subspan(6, 32))};
}
} // namespace

std::optional<TxWireHashes> HashTransactionFromWire(std::span<const std::byte> wire, CoinbaseWitnessData* coinbase)
{
    SpanReader reader{wire};
    const size_t total = wire.size();
    const auto consumed = [&] { return total - reader.size(); };

    try {
        reader.ignore(4); // version
        const size_t after_version = consumed();

        // Mirror UnserializeTransaction(): read the input vector; a zero count
        // followed by a non-zero flag is the BIP144 segwit marker, after which
        // the real inputs/outputs follow.
        bool segwit = false;
        size_t legacy_vin_start = after_version; // offset of the vin count in the non-witness form
        uint64_t nin = ReadCompactSize(reader);
        bool have_outputs = true;
        if (nin == 0) {
            uint8_t flag{0};
            reader >> flag;
            if (flag == 0) {
                // A zero-input transaction; no outputs are read, matching the
                // deserializer, and the wire equals the non-witness form.
                have_outputs = false;
            } else {
                if (flag != 1) return std::nullopt; // unknown witness flag bits
                segwit = true;
                legacy_vin_start = consumed(); // past version + marker + flag
                nin = ReadCompactSize(reader);
                SkipInputs(reader, nin);
            }
        } else {
            SkipInputs(reader, nin);
        }

        if (have_outputs) {
            const uint64_t nout = ReadCompactSize(reader);
            for (uint64_t i = 0; i < nout; ++i) {
                reader.ignore(8); // nValue
                const uint64_t slen = ReadCompactSize(reader);
                if (coinbase) {
                    // Examine the scriptPubKey for a witness commitment (last wins).
                    const auto avail = std::min<uint64_t>(slen, reader.size());
                    if (auto c = WitnessCommitment(wire.subspan(consumed(), avail))) coinbase->commitment = c;
                }
                reader.ignore(slen); // scriptPubKey
            }
        }
        const size_t vout_end = consumed();

        if (segwit) {
            bool any_witness_item{false};
            for (uint64_t i = 0; i < nin; ++i) { // one witness stack per input
                const uint64_t items = ReadCompactSize(reader);
                if (items != 0) any_witness_item = true;
                if (coinbase && i == 0 && items == 1) {
                    // The coinbase's reserved value is its sole 32-byte item.
                    // Read it only once the 32 bytes are known to be present;
                    // ignore() below still throws if the item is truncated.
                    const uint64_t ilen = ReadCompactSize(reader);
                    if (ilen == 32 && reader.size() >= 32) {
                        coinbase->reserved = uint256{MakeUCharSpan(wire.subspan(consumed(), 32))};
                    }
                    reader.ignore(ilen);
                } else {
                    for (uint64_t j = 0; j < items; ++j) SkipLengthPrefixed(reader);
                }
            }
            // A segwit-serialized transaction with every witness stack empty is
            // rejected by the deserializer as a superfluous witness record.
            if (!any_witness_item) return std::nullopt;
        }

        const size_t locktime_start = consumed();
        reader.ignore(4); // nLockTime
        const size_t end = consumed();

        TxWireHashes out;
        out.size = end;
        out.has_witness = segwit;

        // wtxid: double-SHA256 of the whole serialized transaction.
        {
            HashWriter hw;
            hw.write(wire.subspan(0, end));
            out.wtxid = hw.GetHash();
        }
        // txid: double-SHA256 of the non-witness serialization. For a segwit
        // transaction that is version + (real vin|vout) + locktime, skipping the
        // marker, flag and witnesses; otherwise it equals the wtxid.
        if (!segwit) {
            out.txid = out.wtxid;
        } else {
            HashWriter hw;
            hw.write(wire.subspan(0, after_version));                              // version
            hw.write(wire.subspan(legacy_vin_start, vout_end - legacy_vin_start)); // vin + vout
            hw.write(wire.subspan(locktime_start, end - locktime_start));          // locktime
            out.txid = hw.GetHash();
        }
        return out;
    } catch (const std::ios_base::failure&) {
        return std::nullopt;
    }
}

BlockBodyCheck CheckBlockBodyCommitments(const uint256& header_merkle_root, std::span<const std::byte> body)
{
    uint64_t ntx{0};
    size_t pos{0};
    {
        SpanReader counter{body};
        try {
            ntx = ReadCompactSize(counter);
        } catch (const std::ios_base::failure&) {
            return {BlockBodyStatus::MALFORMED, false}; // cannot even read the transaction count
        }
        pos = body.size() - counter.size(); // bytes the count occupied
    }
    // An empty block is cheap to handle; leave it to the normal path.
    if (ntx == 0) return {BlockBodyStatus::MATCHES, false};

    // Walk every transaction, collecting txids and wtxids and (from the
    // coinbase) the commitment and reserved value. Grow the vectors as we go
    // rather than reserving the claimed count, which the wire does not bound.
    std::vector<uint256> txids;
    std::vector<uint256> wtxids;
    bool has_witness{false};
    CoinbaseWitnessData coinbase;
    for (uint64_t i = 0; i < ntx; ++i) {
        if (pos > body.size()) return {BlockBodyStatus::MALFORMED, has_witness};
        const auto tx = HashTransactionFromWire(body.subspan(pos), i == 0 ? &coinbase : nullptr);
        if (!tx) return {BlockBodyStatus::MALFORMED, has_witness};
        txids.push_back(tx->txid);
        wtxids.push_back(tx->wtxid);
        has_witness |= tx->has_witness;
        pos += tx->size;
    }

    // The transaction tree must commit to exactly these txids, with no
    // duplicate-txid malleation (mirrors CheckBlock's merkle-root check).
    bool mutated{false};
    if (ComputeMerkleRoot(std::move(txids), &mutated) != header_merkle_root || mutated) {
        return {BlockBodyStatus::MUTATED, has_witness};
    }

    // Witness commitment (mirrors CheckWitnessMalleation with segwit active).
    if (coinbase.commitment) {
        if (!coinbase.reserved) return {BlockBodyStatus::MUTATED, has_witness}; // needs a 32-byte reserved value
        wtxids[0] = uint256{};                                                  // the coinbase's witness hash is 0 by definition
        uint256 expected = ComputeMerkleRoot(std::move(wtxids));
        CHash256().Write(expected).Write(*coinbase.reserved).Finalize(expected);
        if (expected != *coinbase.commitment) return {BlockBodyStatus::MUTATED, has_witness};
    } else if (has_witness) {
        return {BlockBodyStatus::MUTATED, has_witness}; // witness data without a commitment is not allowed
    }
    return {BlockBodyStatus::MATCHES, has_witness};
}

} // namespace node
