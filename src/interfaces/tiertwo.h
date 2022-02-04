// Copyright (c) 2022 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_INTERFACES_TIERTWO_H
#define PIVX_INTERFACES_TIERTWO_H

#include "sync.h"
#include "uint256.h"
#include "validationinterface.h"

#include <vector>

class DMNView {
public:
    uint64_t id; // DMN identifier
    uint256 proTxHash;
    bool hasOwnerKey{false};
    bool hasVotingKey{false};
    bool hasPayoutScript{false};
    bool isPoSeBanned{false};

    Optional<std::string> ownerAddrLabel{nullopt};
    Optional<std::string> votingAddrLabel{nullopt};
    Optional<std::string> payoutAddrLabel{nullopt};

    std::string service;

    COutPoint collateralOut;
};

namespace interfaces {

class TierTwo : public CValidationInterface {
// todo: Store a cache of the active DMNs that this wallet knows
// Update state via the validation interface signal MasternodesChanges etc..
private:
    RecursiveMutex cs_cache;
    std::vector<std::shared_ptr<DMNView>> m_cached_dmns GUARDED_BY(cs_cache);
    uint256 m_last_block_cached GUARDED_BY(cs_cache);

    // Refresh the cached values from 'mnList'
    void refreshCache(const CDeterministicMNList& mnList);
public:
    // Initialize cache
    void init();

    // Return true if the bls key is valid
    bool isBlsPubKeyValid(const std::string& blsKey);

    // Return the DMNs that this wallet "owns".
    // future: add filter to return by owner, operator, voter or a combination of them.
    std::vector<std::shared_ptr<DMNView>> getKnownDMNs() { return WITH_LOCK(cs_cache, return m_cached_dmns;); };

    void NotifyMasternodeListChanged(bool undo, const CDeterministicMNList& oldMNList, const CDeterministicMNListDiff& diff) override;
};

extern std::unique_ptr<TierTwo> g_tiertwo;

} // end namespace interfaces


#endif //PIVX_INTERFACES_TIERTWO_H
