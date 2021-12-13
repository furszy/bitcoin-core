// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_TIERTWO_INIT_H
#define PIVX_TIERTWO_INIT_H

static const bool DEFAULT_MASTERNODE  = false;

/** Loads from disk all the tier two related objects */
bool LoadTierTwo(int chain_active_height);

/** Register all tier two objects */
void RegisterTierTwoValidationInterface();

/** Dump tier two managers to disk */
void DumpTierTwo();

void SetBudgetFinMode(const std::string& mode);

/** Initialize the active Masternode manager */
bool InitActiveMN();


#endif //PIVX_TIERTWO_INIT_H
