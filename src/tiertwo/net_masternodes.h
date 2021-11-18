// Copyright (c) 2020 The Dash developers
// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_NET_MASTERNODES_H
#define PIVX_NET_MASTERNODES_H

#include "consensus/params.h"
#include "sync.h"
#include "threadinterrupt.h"
#include "uint256.h"

#include <thread>

class CAddress;
class CConnman;
class CChainParams;
class CNode;
class CScheduler;

class TierTwoConnMan
{
public:
    TierTwoConnMan(CConnman* _connman);
    ~TierTwoConnMan();

    // Add or update quorum nodes
    void setQuorumNodes(Consensus::LLMQType llmqType,
                        const uint256& quorumHash,
                        const std::set<uint256>& proTxHashes);

    // Return true if the quorum was already registered
    bool hasQuorumNodes(Consensus::LLMQType llmqType, const uint256& quorumHash);

    // Remove the registered quorum from the pending/protected MN connections
    void removeQuorumNodes(Consensus::LLMQType llmqType, const uint256& quorumHash);

    // Returns true if the node has the same address as a MN.
    bool isMasternodeQuorumNode(const CNode* pnode);

    // Add DMN to the pending connection list
    bool addPendingMasternode(const uint256& proTxHash);

    // Adds the DMNs to the pending to probe list
    void addPendingProbeConnections(const std::set<uint256>& proTxHashes);

    // Manages the MN connections
    void ThreadOpenMasternodeConnections();
    void start(CScheduler& scheduler);
    void stop();
    void interrupt();

private:
    CThreadInterrupt interruptNet;
    std::thread threadOpenMasternodeConnections;

    mutable RecursiveMutex cs_vPendingMasternodes;
    std::vector<uint256> vPendingMasternodes GUARDED_BY(cs_vPendingMasternodes);
    typedef std::pair<Consensus::LLMQType, uint256> QuorumTypeAndHash;
    std::map<QuorumTypeAndHash, std::set<uint256>> masternodeQuorumNodes GUARDED_BY(cs_vPendingMasternodes);
    std::set<uint256> masternodePendingProbes GUARDED_BY(cs_vPendingMasternodes);

    // parent connections manager
    CConnman* connman;

    void openConnection(const CAddress& addrConnect, bool isProbe);
    void doMaintenance();
};

#endif //PIVX_NET_MASTERNODES_H
