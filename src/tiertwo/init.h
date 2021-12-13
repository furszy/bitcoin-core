// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_TIERTWO_INIT_H
#define PIVX_TIERTWO_INIT_H

#include <string>

static const bool DEFAULT_MASTERNODE  = false;

class CScheduler;
namespace boost {
    class thread_group;
}

/** Loads from disk all the tier two related objects */
bool LoadTierTwo(int chain_active_height);

/** Register all tier two objects */
void RegisterTierTwoValidationInterface();

/** Dump tier two managers to disk */
void DumpTierTwo();

void SetBudgetFinMode(const std::string& mode);

/** Initialize the active Masternode manager */
bool InitActiveMN();

/** Starts tier two threads and jobs */
void StartTierTwoThreadsAndScheduleJobs(boost::thread_group& threadGroup, CScheduler& scheduler);


#endif //PIVX_TIERTWO_INIT_H
