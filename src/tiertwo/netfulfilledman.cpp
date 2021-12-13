// Copyright (c) 2014-2020 The Dash Core developers
// Copyright (c) 2021 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include "tiertwo/netfulfilledman.h"
#include "chainparams.h"
#include "netaddress.h"
#include "shutdown.h"
#include "utiltime.h"

CNetFulfilledRequestManager g_netfulfilledman;

void CNetFulfilledRequestManager::AddFulfilledRequest(const CService& addr, const std::string& strRequest)
{
    LOCK(cs_mapFulfilledRequests);
    mapFulfilledRequests[addr][strRequest] = GetTime() + Params().FulfilledRequestExpireTime();
}

bool CNetFulfilledRequestManager::HasFulfilledRequest(const CService& addr, const std::string& strRequest)
{
    LOCK(cs_mapFulfilledRequests);
    auto it = mapFulfilledRequests.find(addr);
    if (it != mapFulfilledRequests.end()) {
        auto itReq = it->second.find(strRequest);
        if (itReq != it->second.end()) {
            return it->second[strRequest] > GetTime();
        }
    }
    return false;
}

void CNetFulfilledRequestManager::RemoveFulfilledRequest(const CService& addr, const std::string& strRequest)
{
    LOCK(cs_mapFulfilledRequests);
    auto it = mapFulfilledRequests.find(addr);
    if (it != mapFulfilledRequests.end()) {
        it->second.erase(strRequest);
    }
}

void CNetFulfilledRequestManager::RemoveAllFulfilledRequests(const CService& addr)
{
    LOCK(cs_mapFulfilledRequests);
    mapFulfilledRequests.erase(addr);
}

void CNetFulfilledRequestManager::CheckAndRemove()
{
    LOCK(cs_mapFulfilledRequests);
    int64_t now = GetTime();
    for (auto it = mapFulfilledRequests.begin(); it != mapFulfilledRequests.end();) {
        for (auto it_entry = it->second.begin(); it_entry != it->second.end();) {
            if (now > it_entry->second) {
                it_entry = it->second.erase(it_entry);
            } else {
                it_entry++;
            }
        }
        if (it->second.empty()) {
            it = mapFulfilledRequests.erase(it);
        } else {
            it++;
        }
    }
}

void CNetFulfilledRequestManager::Clear()
{
    LOCK(cs_mapFulfilledRequests);
    mapFulfilledRequests.clear();
}

std::string CNetFulfilledRequestManager::ToString() const
{
    std::ostringstream info;
    info << "Nodes with fulfilled requests: " << (int)mapFulfilledRequests.size();
    return info.str();
}

void CNetFulfilledRequestManager::DoMaintenance()
{
    if (ShutdownRequested()) return;
    CheckAndRemove();
}
