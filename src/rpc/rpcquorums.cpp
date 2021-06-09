// Copyright (c) 2018-2021 The Dash Core developers
// Copyright (c) 2022 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "activemasternode.h"
#include "chainparams.h"
#include "llmq/quorums_blockprocessor.h"
#include "llmq/quorums_commitment.h"
#include "llmq/quorums_debug.h"
#include "llmq/quorums_utils.h"
#include "net.h"
#include "rpc/server.h"
#include "validation.h"


UniValue quorumdkgstatus(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() > 1) {
        throw std::runtime_error(
                "quorumdkgstatus ( detail_level )\n"
                "Return the status of the current DKG process of the active masternode.\n"
                "\nArguments:\n"
                "1. detail_level         (number, optional, default=0) Detail level of output.\n"
                "                        0=Only show counts. 1=Show member indexes. 2=Show member's ProTxHashes.\n"
                "\nExamples:\n"
                + HelpExampleRpc("quorumdkgstatus", "2")
                + HelpExampleCli("quorumdkgstatus", "")
        );
    }

    int detailLevel = request.params.size() > 0 ? request.params[0].get_int() : 0;
    if (detailLevel < 0 || detailLevel > 2) {
        throw JSONRPCError(RPC_INVALID_PARAMETER, strprintf("invalid detail_level %d", detailLevel));
    }

    if (!fMasterNode || !activeMasternodeManager) {
        throw JSONRPCError(RPC_INVALID_PARAMETER, "This is not a (deterministic) masternode");
    }

    llmq::CDKGDebugStatus status;
    llmq::quorumDKGDebugManager->GetLocalDebugStatus(status);

    auto ret = status.ToJson(detailLevel);

    const int tipHeight = WITH_LOCK(cs_main, return chainActive.Height(); );

    UniValue minableCommitments(UniValue::VOBJ);
    for (const auto& p : Params().GetConsensus().llmqs) {
        auto& params = p.second;
        llmq::CFinalCommitment fqc;
        if (llmq::quorumBlockProcessor->GetMinableCommitment(params.type, tipHeight, fqc)) {
            UniValue obj(UniValue::VOBJ);
            fqc.ToJson(obj);
            minableCommitments.pushKV(params.name, obj);
        }
    }
    ret.pushKV("minableCommitments", minableCommitments);

    return ret;
}

static const CRPCCommand commands[] =
{ //  category       name                      actor (function)      okSafe argNames
  //  -------------- ------------------------- --------------------- ------ --------
    { "evo",         "quorumdkgstatus",        &quorumdkgstatus,     true,  {"detail_level"}  },
};

void RegisterQuorumsRPCCommands(CRPCTable& tableRPC)
{
    for (unsigned int vcidx = 0; vcidx < ARRAYLEN(commands); vcidx++)
        tableRPC.appendCommand(commands[vcidx].name, &commands[vcidx]);
}
