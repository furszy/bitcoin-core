// Copyright (c) 2014-2020 The Dash Core developers
// Copyright (c) 2021 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_NETFULFILLEDMAN_H
#define PIVX_NETFULFILLEDMAN_H

#include "serialize.h"
#include "sync.h"

#include <map>

class CService;

// Fulfilled requests are used to prevent nodes from asking the same data on sync
// and being banned for doing it too often.
class CNetFulfilledRequestManager
{
private:
    typedef std::map<std::string, int64_t> fulfilledreqmapentry_t;
    typedef std::map<CService, fulfilledreqmapentry_t> fulfilledreqmap_t;

    // Keep track of what node has/was asked for and when
    fulfilledreqmap_t mapFulfilledRequests;
    mutable Mutex cs_mapFulfilledRequests;

    void RemoveFulfilledRequest(const CService& addr, const std::string& strRequest);

public:
    CNetFulfilledRequestManager() = default;

    SERIALIZE_METHODS(CNetFulfilledRequestManager, obj) {
        LOCK(obj.cs_mapFulfilledRequests);
        READWRITE(obj.mapFulfilledRequests);
    }

    void AddFulfilledRequest(const CService& addr, const std::string& strRequest);
    bool HasFulfilledRequest(const CService& addr, const std::string& strRequest);
    void RemoveAllFulfilledRequests(const CService& addr);

    void CheckAndRemove();
    void Clear();

    std::string ToString() const;

    void DoMaintenance();
};

extern CNetFulfilledRequestManager g_netfulfilledman;

#endif // PIVX_NETFULFILLEDMAN_H
