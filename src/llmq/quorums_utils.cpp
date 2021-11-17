// Copyright (c) 2018-2019 The Dash Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "llmq/quorums_utils.h"

#include "bls/bls_wrapper.h"
#include "chainparams.h"
#include "random.h"
#include "spork.h"

namespace llmq
{

namespace utils
{

uint256 BuildCommitmentHash(Consensus::LLMQType llmqType, const uint256& blockHash, const std::vector<bool>& validMembers, const CBLSPublicKey& pubKey, const uint256& vvecHash)
{
    CHashWriter hw(SER_NETWORK, 0);
    hw << static_cast<uint8_t>(llmqType);
    hw << blockHash;
    hw << DYNBITSET(validMembers);
    hw << pubKey;
    hw << vvecHash;
    return hw.GetHash();
}

uint256 BuildSignHash(Consensus::LLMQType llmqType, const uint256& quorumHash, const uint256& id, const uint256& msgHash)
{
    CHashWriter h(SER_GETHASH, 0);
    h << static_cast<uint8_t>(llmqType);
    h << quorumHash;
    h << id;
    h << msgHash;
    return h.GetHash();
}

std::string ToHexStr(const std::vector<bool>& vBits)
{
    std::vector<uint8_t> vBytes((vBits.size() + 7) / 8);
    for (size_t i = 0; i < vBits.size(); i++) {
        vBytes[i / 8] |= vBits[i] << (i % 8);
    }
    return HexStr(vBytes);
}

uint256 DeterministicOutboundConnection(const uint256& proTxHash1, const uint256& proTxHash2)
{
    // We need to deterministically select who is going to initiate the connection. The naive way would be to simply
    // return the min(proTxHash1, proTxHash2), but this would create a bias towards MNs with a numerically low
    // hash. To fix this, we return the proTxHash that has the lowest value of:
    //   hash(min(proTxHash1, proTxHash2), max(proTxHash1, proTxHash2), proTxHashX)
    // where proTxHashX is the proTxHash to compare
    uint256 h1;
    uint256 h2;
    if (proTxHash1 < proTxHash2) {
        h1 = ::SerializeHash(std::make_tuple(proTxHash1, proTxHash2, proTxHash1));
        h2 = ::SerializeHash(std::make_tuple(proTxHash1, proTxHash2, proTxHash2));
    } else {
        h1 = ::SerializeHash(std::make_tuple(proTxHash2, proTxHash1, proTxHash1));
        h2 = ::SerializeHash(std::make_tuple(proTxHash2, proTxHash1, proTxHash2));
    }
    if (h1 < h2) {
        return proTxHash1;
    }
    return proTxHash2;
}

} // namespace llmq::utils

} // namespace llmq
