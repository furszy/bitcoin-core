// Copyright (c) 2021 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_TIERTWO_SYNC_STATE_H
#define PIVX_TIERTWO_SYNC_STATE_H

#include <atomic>

class TierTwoSyncState {
public:
    bool IsBlockchainSynced() { return fBlockchainSynced; };

    // Only called from masternodesync
    void SetBlockchainSync(bool f) { fBlockchainSynced = f; };

private:
    std::atomic<bool> fBlockchainSynced{false};
};

extern TierTwoSyncState g_tiertwo_sync_state;

#endif //PIVX_TIERTWO_SYNC_STATE_H
