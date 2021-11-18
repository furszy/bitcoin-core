// Copyright (c) 2020 The Dash developers
// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include "tiertwo/net_masternodes.h"

#include "chainparams.h"
#include "evo/deterministicmns.h"
#include "scheduler.h"
#include "util/system.h" // for gArgs
#include "tiertwo/masternode_meta_manager.h" // for g_mmetaman
#include "masternode-sync.h" // for IsBlockchainSynced

TierTwoConnMan::TierTwoConnMan(CConnman* _connman) : connman(_connman) {}
TierTwoConnMan::~TierTwoConnMan() { connman = nullptr; }

void TierTwoConnMan::setQuorumNodes(Consensus::LLMQType llmqType,
                                    const uint256& quorumHash,
                                    const std::set<uint256>& proTxHashes)
{
    LOCK(cs_vPendingMasternodes);
    auto it = masternodeQuorumNodes.emplace(QuorumTypeAndHash(llmqType, quorumHash), proTxHashes);
    if (!it.second) {
        it.first->second = proTxHashes;
    }
}

bool TierTwoConnMan::hasQuorumNodes(Consensus::LLMQType llmqType, const uint256& quorumHash)
{
    LOCK(cs_vPendingMasternodes);
    return masternodeQuorumNodes.count(QuorumTypeAndHash(llmqType, quorumHash));
}

void TierTwoConnMan::removeQuorumNodes(Consensus::LLMQType llmqType, const uint256& quorumHash)
{
    LOCK(cs_vPendingMasternodes);
    masternodeQuorumNodes.erase(std::make_pair(llmqType, quorumHash));
}

bool TierTwoConnMan::isMasternodeQuorumNode(const CNode* pnode)
{
    // Let's see if this is an outgoing connection to an address that is known to be a masternode
    // We however only need to know this if the node did not authenticate itself as a MN yet
    uint256 assumedProTxHash;
    if (pnode->verifiedProRegTxHash.IsNull() && !pnode->fInbound) {
        auto mnList = deterministicMNManager->GetListAtChainTip();
        auto dmn = mnList.GetMNByService(pnode->addr);
        if (dmn == nullptr) {
            // This is definitely not a masternode
            return false;
        }
        assumedProTxHash = dmn->proTxHash;
    }

    LOCK(cs_vPendingMasternodes);
    for (const auto& quorumConn : masternodeQuorumNodes) {
        if (!pnode->verifiedProRegTxHash.IsNull()) {
            if (quorumConn.second.count(pnode->verifiedProRegTxHash)) {
                return true;
            }
        } else if (!assumedProTxHash.IsNull()) {
            if (quorumConn.second.count(assumedProTxHash)) {
                return true;
            }
        }
    }
    return false;
}

void TierTwoConnMan::start(CScheduler& scheduler)
{
    // Must be started after connman
    assert(connman);
    interruptNet.reset();

    // Connecting to specific addresses, no masternode connections available
    if (gArgs.IsArgSet("-connect") && gArgs.GetArgs("-connect").size() > 0)
        return;
    // Initiate masternode connections
    threadOpenMasternodeConnections = std::thread(&TraceThread<std::function<void()> >, "mncon", std::function<void()>(std::bind(&TierTwoConnMan::ThreadOpenMasternodeConnections, this)));
    // Cleanup process every 60 seconds
    scheduler.scheduleEvery(std::bind(&TierTwoConnMan::doMaintenance, this), 60 * 1000);
}

void TierTwoConnMan::stop() {
    if (threadOpenMasternodeConnections.joinable()) {
        threadOpenMasternodeConnections.join();
    }
}

void TierTwoConnMan::interrupt()
{
    interruptNet();
}

void TierTwoConnMan::openConnection(const CAddress& addrConnect)
{
    if (interruptNet) return;
    connman->OpenNetworkConnection(addrConnect, false, nullptr, nullptr, false, false, false, true);
}

class PeerData {
public:
    PeerData(const CService& s, bool disconnect, bool is_mn_conn) : service(s), f_disconnect(disconnect), f_is_mn_conn(is_mn_conn) {}
    const CService service;
    bool f_disconnect{false};
    bool f_is_mn_conn{false};
    bool operator==(const CService& s) const { return service == s; }
};

void TierTwoConnMan::ThreadOpenMasternodeConnections()
{
    const auto& chainParams = Params();
    bool triedConnect = false;
    while (!interruptNet) {

        // Retry every 5 seconds if a connection was created, otherwise 30 seconds
        int sleepTime = triedConnect ? 5000 : 30000;
        if (!interruptNet.sleep_for(std::chrono::milliseconds(sleepTime))) {
            return;
        }

        triedConnect = false;

        // todo: add !fNetworkActive
        if (!masternodeSync.IsBlockchainSynced()) {
            continue;
        }

        // Gather all connected peers first, so we don't
        // try to connect to an already connected peer
        std::vector<PeerData> connectedNodes;
        std::set<uint256> connectedProRegTxHashes;
        connman->ForEachNode([&](const CNode* pnode) {
            connectedNodes.emplace_back(PeerData{pnode->addr, pnode->fDisconnect, pnode->m_masternode_connection});
            if (!pnode->verifiedProRegTxHash.IsNull()) {
                connectedProRegTxHashes.emplace(pnode->verifiedProRegTxHash);
            }
        });

        // Try to connect to a single MN per cycle
        CDeterministicMNCPtr dmnToConnect{nullptr};
        // Current list
        auto mnList = deterministicMNManager->GetListAtChainTip();
        int64_t currentTime = GetAdjustedTime();
        {
            LOCK(cs_vPendingMasternodes);
            std::vector<CDeterministicMNCPtr> pending;
            for (const auto& group: masternodeQuorumNodes) {
                for (const auto& proRegTxHash: group.second) {
                    // Skip if already have this member connected
                    if (connectedProRegTxHashes.count(proRegTxHash)) continue;

                    // Check if DMN exists in tip list
                    const auto& dmn = mnList.GetValidMN(proRegTxHash);
                    if (!dmn) continue;
                    auto peerData = std::find(connectedNodes.begin(), connectedNodes.end(), dmn->pdmnState->addr);

                    // Skip already connected nodes.
                    if (peerData != std::end(connectedNodes) && (peerData->f_disconnect || peerData->f_is_mn_conn)) {
                        continue;
                    }

                    // Check if we already tried this connection recently to not retry too often
                    int64_t lastAttempt = g_mmetaman.GetMetaInfo(dmn->proTxHash)->GetLastOutboundAttempt();
                    // back off trying connecting to an address if we already tried recently
                    if (currentTime - lastAttempt < chainParams.LLMQConnectionRetryTimeout()) {
                        continue;
                    }
                    pending.emplace_back(dmn);
                }
            }
            // todo: add proving system.
            // Select a random node to connect
            if (!pending.empty()) {
                dmnToConnect = pending[GetRandInt((int)pending.size())];
                LogPrint(BCLog::NET_MN, "TierTwoConnMan::%s -- opening quorum connection to %s, service=%s\n",
                         __func__, dmnToConnect->proTxHash.ToString(), dmnToConnect->pdmnState->addr.ToString());
            }
        }

        // No DMN to connect
        if (!dmnToConnect || interruptNet) {
            continue;
        }

        // Update last attempt and try connection
        g_mmetaman.GetMetaInfo(dmnToConnect->proTxHash)->SetLastOutboundAttempt(currentTime);
        triedConnect = true;

        // Now connect
        openConnection(CAddress(dmnToConnect->pdmnState->addr, NODE_NETWORK));
        // should be in the list now if connection was opened
        bool connected = connman->ForNode(dmnToConnect->pdmnState->addr, CConnman::AllNodes, [&](CNode* pnode) {
            if (pnode->fDisconnect) {
                return false;
            }
            return true;
        });
        if (!connected) {
            LogPrint(BCLog::NET_MN, "TierTwoConnMan::%s -- connection failed for masternode  %s, service=%s\n",
                     __func__, dmnToConnect->proTxHash.ToString(), dmnToConnect->pdmnState->addr.ToString());
            // reset last outbound success
            g_mmetaman.GetMetaInfo(dmnToConnect->proTxHash)->SetLastOutboundSuccess(0);
        }
    }
}

static void ProcessMasternodeConnections(CConnman& connman, TierTwoConnMan& tierTwoConnMan)
{
    // Don't disconnect masternode connections when we have less than the desired amount of outbound nodes
    int nonMasternodeCount = 0;
    connman.ForEachNode([&](CNode* pnode) {
        if (!pnode->fInbound && !pnode->fFeeler && !pnode->fAddnode && !pnode->m_masternode_connection && !pnode->m_masternode_probe_connection) {
            nonMasternodeCount++;
        }
    });
    if (nonMasternodeCount < (int) connman.GetMaxOutboundNodeCount()) {
        return;
    }

    connman.ForEachNode([&](CNode* pnode) {
        // we're only disconnecting m_masternode_connection connections
        if (!pnode->m_masternode_connection) return;
        // we're only disconnecting outbound connections (inbound connections are disconnected in AcceptConnection())
        if (pnode->fInbound) return;
        // we're not disconnecting LLMQ connections
        if (tierTwoConnMan.isMasternodeQuorumNode(pnode)) return;
        // we're not disconnecting masternode probes for at least a few seconds
        if (pnode->m_masternode_probe_connection && GetSystemTimeInSeconds() - pnode->nTimeConnected < 5) return;

        if (fLogIPs) {
            LogPrintf("Closing Masternode connection: peer=%d, addr=%s\n", pnode->GetId(), pnode->addr.ToString());
        } else {
            LogPrintf("Closing Masternode connection: peer=%d\n", pnode->GetId());
        }
        pnode->fDisconnect = true;
    });
}

void TierTwoConnMan::doMaintenance()
{
    if(!masternodeSync.IsBlockchainSynced() || interruptNet) {
        return;
    }
    ProcessMasternodeConnections(*connman, *this);
}

