// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_BLOCK_WIRE_CHECK_H
#define BITCOIN_NODE_BLOCK_WIRE_CHECK_H

#include <uint256.h>

#include <cstddef>
#include <optional>
#include <span>

namespace node {

/** The txid and wtxid of a transaction, and the number of wire bytes it spans,
 *  computed straight from its serialized form without materializing a
 *  CTransaction (so a witness-heavy transaction is never expanded in memory). */
struct TxWireHashes {
    uint256 txid;
    uint256 wtxid;
    size_t size;
    bool has_witness; //!< the transaction was serialized with a segwit marker
};

/** The two coinbase fields a block's witness commitment is checked against,
 *  pulled out of the coinbase's wire bytes as it is walked. Each is set only
 *  when present and well-formed, so an absent field means "not committed". */
struct CoinbaseWitnessData {
    //! 32-byte payload of the last `OP_RETURN 0x24 0xaa21a9ed` output, if any.
    std::optional<uint256> commitment;
    //! The coinbase's sole 32-byte witness item (BIP141 reserved value), if any.
    std::optional<uint256> reserved;
};

/** Compute the txid and wtxid of the transaction serialized at the start of
 *  `wire`, and how many bytes it occupies, by walking the wire in place.
 *
 *  If `coinbase` is non-null, the walk also extracts the witness commitment and
 *  reserved value (see CoinbaseWitnessData); pass it only for the coinbase.
 *
 *  Returns std::nullopt if `wire` does not begin with a structurally
 *  well-formed transaction (truncated, bad lengths, unknown witness flag). The
 *  hashes it returns match CTransaction::GetHash() / GetWitnessHash() for every
 *  transaction the normal deserializer accepts; this is relied upon and checked
 *  by a differential fuzz target. */
std::optional<TxWireHashes> HashTransactionFromWire(std::span<const std::byte> wire,
                                                    CoinbaseWitnessData* coinbase = nullptr);

/** Whether a block body's transactions match its commitments. */
enum class BlockBodyStatus {
    MATCHES,   //!< transactions hash to the merkle root and the witness commitment holds
    MUTATED,   //!< well-formed, but a commitment does not match (a mutated block)
    MALFORMED, //!< not a well-formed transaction sequence (the deserializer would throw)
};

/** Result of CheckBlockBodyCommitments(). */
struct BlockBodyCheck {
    BlockBodyStatus status;
    //! Whether any transaction carried witness data. Deserializing a block is
    //! only expensive -- the witness-expansion attack this guards against --
    //! when it has witness data; a caller may ignore a non-matching status on a
    //! body without witness, where deserialization is bounded and cheap.
    bool has_witness;
};

/** Check a block's transactions against its commitments without materializing
 *  them. `body` is a block minus its 80-byte header: the transaction count
 *  followed by each transaction's wire serialization.
 *
 *  The status is MATCHES only if the transactions hash to `header_merkle_root`
 *  (with no duplicate-txid mutation) and the witness rule holds: either the
 *  coinbase carries a commitment that the transactions' witness root and the
 *  coinbase's reserved value satisfy, or no transaction carries witness data.
 *  This mirrors the merkle-root and witness-commitment checks a full CheckBlock
 *  performs with segwit active.
 *
 *  MUTATED means a well-formed body whose commitments do not match -- it would
 *  be rejected as mutated after a costly deserialization. MALFORMED means the
 *  bytes are not a valid transaction sequence, exactly what the deserializer
 *  would throw on. An empty transaction count yields MATCHES: that degenerate
 *  block is cheap and handled downstream. */
BlockBodyCheck CheckBlockBodyCommitments(const uint256& header_merkle_root, std::span<const std::byte> body);

} // namespace node

#endif // BITCOIN_NODE_BLOCK_WIRE_CHECK_H
