// Copyright (c) 2021 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_TIERTWO_SYNC_STATE_H
#define PIVX_TIERTWO_SYNC_STATE_H

#include <atomic>
#include <map>

#define MASTERNODE_SYNC_INITIAL 0
#define MASTERNODE_SYNC_SPORKS 1
#define MASTERNODE_SYNC_LIST 2
#define MASTERNODE_SYNC_MNW 3
#define MASTERNODE_SYNC_BUDGET 4
#define MASTERNODE_SYNC_BUDGET_PROP 10
#define MASTERNODE_SYNC_BUDGET_FIN 11
#define MASTERNODE_SYNC_FAILED 998
#define MASTERNODE_SYNC_FINISHED 999

// Sync threshold
#define MASTERNODE_SYNC_THRESHOLD 2

class uint256;

class TierTwoSyncState {
public:
    bool IsBlockchainSynced() { return fBlockchainSynced; };
    bool IsSynced() { return m_current_sync_phase == MASTERNODE_SYNC_FINISHED; }
    bool IsSporkListSynced() { return m_current_sync_phase > MASTERNODE_SYNC_SPORKS; }
    bool IsMasternodeListSynced() { return m_current_sync_phase > MASTERNODE_SYNC_LIST; }

    // Update seen maps
    void AddedMasternodeList(const uint256& hash);
    void AddedMasternodeWinner(const uint256& hash);
    void AddedBudgetItem(const uint256& hash);

    int64_t GetlastMasternodeList() { return lastMasternodeList; }
    int64_t GetlastMasternodeWinner() { return lastMasternodeWinner; }
    int64_t GetlastBudgetItem() { return lastBudgetItem; }

    void EraseSeenMNB(const uint256& hash) { mapSeenSyncMNB.erase(hash); }
    void EraseSeenMNW(const uint256& hash) { mapSeenSyncMNW.erase(hash); }
    void EraseSeenSyncBudget(const uint256& hash) { mapSeenSyncBudget.erase(hash); }

    // Reset seen data
    void resetData();

    // Only called from masternodesync and unit tests.
    void setBlockchainSync(bool f) { fBlockchainSynced = f; };
    void setCurrentSyncPhase(int sync_phase) { m_current_sync_phase = sync_phase; };
    int getSyncPhase() { return m_current_sync_phase; }

private:
    std::atomic<bool> fBlockchainSynced{false};
    std::atomic<int> m_current_sync_phase{0};

    // Seen elements
    std::map<uint256, int> mapSeenSyncMNB;
    std::map<uint256, int> mapSeenSyncMNW;
    std::map<uint256, int> mapSeenSyncBudget;
    // Last seen time
    int64_t lastMasternodeList{0};
    int64_t lastMasternodeWinner{0};
    int64_t lastBudgetItem{0};
};

extern TierTwoSyncState g_tiertwo_sync_state;

#endif //PIVX_TIERTWO_SYNC_STATE_H
