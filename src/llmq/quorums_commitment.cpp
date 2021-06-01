// Copyright (c) 2018-2019 The Dash Core developers
// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "llmq/quorums_commitment.h"

#include "chainparams.h"
#include "evo/specialtx.h"
#include "llmq/quorums_utils.h"
#include "logging.h"
#include "validation.h"


namespace llmq
{

CFinalCommitment::CFinalCommitment(const Consensus::LLMQParams& params, const uint256& _quorumHash) :
        llmqType(params.type),
        quorumHash(_quorumHash),
        signers(params.size),
        validMembers(params.size)
{
}

bool CFinalCommitment::IsNull() const
{
    if (CountSigners() > 0 || CountValidMembers() > 0) {
        return false;
    }

    if (quorumPublicKey.IsValid() ||
        !quorumVvecHash.IsNull() ||
        membersSig.IsValid() ||
        quorumSig.IsValid()) {
        return false;
    }

    return true;
}

void CFinalCommitment::ToJson(UniValue& obj) const
{
    obj.setObject();
    obj.pushKV("version", (int)nVersion);
    obj.pushKV("llmqType", (int)llmqType);
    obj.pushKV("quorumHash", quorumHash.ToString());
    obj.pushKV("signersCount", CountSigners());
    obj.pushKV("signers", utils::ToHexStr(signers));
    obj.pushKV("validMembersCount", CountValidMembers());
    obj.pushKV("validMembers", utils::ToHexStr(validMembers));
    obj.pushKV("quorumPublicKey", quorumPublicKey.ToString());
    obj.pushKV("quorumVvecHash", quorumVvecHash.ToString());
    obj.pushKV("quorumSig", quorumSig.ToString());
    obj.pushKV("membersSig", membersSig.ToString());
}

template<typename... Args>
static bool errorFinalCommitment(const char* fmt, const Args&... args)
{
    try {
        LogPrintf("Invalid Final Commitment -- %s\n", tfm::format(fmt, args...));
    } catch (tinyformat::format_error &e) {
        LogPrintf("Error (%s) while formatting message %s\n", std::string(e.what()), fmt);
    }
    return false;
}

bool CFinalCommitment::Verify(const CBlockIndex* pQuorumIndex, bool checkSigs) const
{
    if (nVersion == 0 || nVersion > CURRENT_VERSION) {
        return errorFinalCommitment("version (%d)", nVersion);
    }

    if (!Params().GetConsensus().llmqs.count((Consensus::LLMQType)llmqType)) {
        return errorFinalCommitment("type (%d)", llmqType);
    }
    const auto& params = Params().GetConsensus().llmqs.at((Consensus::LLMQType)llmqType);

    if (!VerifySizes(params)) {
        return errorFinalCommitment("sizes");
    }

    if (IsNull()) {
        return true;
    }

    int count_validmembers = CountValidMembers();
    if (count_validmembers < params.minSize) {
        return errorFinalCommitment("valid members count (%d < %d)", count_validmembers, params.minSize);
    }
    int count_signers = CountSigners();
    if (count_signers < params.minSize) {
        return errorFinalCommitment("signers count (%d < %d)", count_signers, params.minSize);
    }

    if (!quorumPublicKey.IsValid()) {
        return errorFinalCommitment("public key");
    }
    if (quorumVvecHash.IsNull()) {
        return errorFinalCommitment("quorumVvecHash");
    }
    if (!membersSig.IsValid()) {
        return errorFinalCommitment("membersSig");
    }
    if (!quorumSig.IsValid()) {
        return errorFinalCommitment("quorumSig");
    }

    auto members = utils::GetAllQuorumMembers(params.type, pQuorumIndex);
    for (size_t i = members.size(); i < params.size; i++) {
        if (validMembers[i]) {
            return errorFinalCommitment("validMembers bitset (bit %d should not be set)", i);
        }
        if (signers[i]) {
            return errorFinalCommitment("signers bitset (bit %d should not be set)", i);
        }
    }

    // sigs are only checked when the block is processed
    if (checkSigs) {
        uint256 commitmentHash = utils::BuildCommitmentHash(params.type, quorumHash, validMembers, quorumPublicKey, quorumVvecHash);

        std::vector<CBLSPublicKey> memberPubKeys;
        for (size_t i = 0; i < members.size(); i++) {
            if (!signers[i]) {
                continue;
            }
            memberPubKeys.emplace_back(members[i]->pdmnState->pubKeyOperator.Get());
        }

        if (!membersSig.VerifySecureAggregated(memberPubKeys, commitmentHash)) {
            return errorFinalCommitment("aggregated members signature");
        }

        if (!quorumSig.VerifyInsecure(quorumPublicKey, commitmentHash)) {
            return errorFinalCommitment("invalid quorum signature");
        }
    }

    return true;
}

bool CFinalCommitment::VerifySizes(const Consensus::LLMQParams& params) const
{
    if ((int)signers.size() != params.size) {
        return errorFinalCommitment("signers size (%d != %d)", signers.size(), params.size);
    }
    if ((int)validMembers.size() != params.size) {
        return errorFinalCommitment("validMembers size (%d != %d)", validMembers.size(), params.size);
    }
    return true;
}


} // namespace llmq
