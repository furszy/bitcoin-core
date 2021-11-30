// Copyright (c) 2021 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_TIERTWO_SYNC_STATE_H
#define PIVX_TIERTWO_SYNC_STATE_H

#include <atomic>

#define MASTERNODE_SYNC_INITIAL 0
#define MASTERNODE_SYNC_SPORKS 1
#define MASTERNODE_SYNC_LIST 2
#define MASTERNODE_SYNC_MNW 3
#define MASTERNODE_SYNC_BUDGET 4
#define MASTERNODE_SYNC_BUDGET_PROP 10
#define MASTERNODE_SYNC_BUDGET_FIN 11
#define MASTERNODE_SYNC_FAILED 998
#define MASTERNODE_SYNC_FINISHED 999

class TierTwoSyncState {
public:
    bool IsBlockchainSynced() { return fBlockchainSynced; };
    bool IsSynced() { return m_current_sync_phase == MASTERNODE_SYNC_FINISHED; }
    bool IsSporkListSynced() { return m_current_sync_phase > MASTERNODE_SYNC_SPORKS; }
    bool IsMasternodeListSynced() { return m_current_sync_phase > MASTERNODE_SYNC_LIST; }

    // Only called from masternodesync and unit tests.
    void setBlockchainSync(bool f) { fBlockchainSynced = f; };
    void setCurrentSyncPhase(int sync_phase) { m_current_sync_phase = sync_phase; };
    int getSyncPhase() { return m_current_sync_phase; }

private:
    std::atomic<bool> fBlockchainSynced{false};
    std::atomic<int> m_current_sync_phase{0};
};

extern TierTwoSyncState g_tiertwo_sync_state;

#endif //PIVX_TIERTWO_SYNC_STATE_H
