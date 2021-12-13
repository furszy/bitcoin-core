// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include "tiertwo/init.h"

#include "budget/budgetdb.h"
#include "guiinterface.h"
#include "masternodeman.h"
#include "masternode-payments.h"
#include "validation.h"

// Sets the last CACHED_BLOCK_HASHES hashes into masternode manager cache
static void LoadBlockHashesCache(CMasternodeMan& man)
{
    LOCK(cs_main);
    const CBlockIndex* pindex = chainActive.Tip();
    unsigned int inserted = 0;
    while (pindex && inserted < CACHED_BLOCK_HASHES) {
        man.CacheBlockHash(pindex);
        pindex = pindex->pprev;
        ++inserted;
    }
}

bool LoadTierTwo(int chain_active_height)
{
    // ################################# //
    // ## Legacy Masternodes Manager ### //
    // ################################# //
    uiInterface.InitMessage(_("Loading masternode cache..."));

    mnodeman.SetBestHeight(chain_active_height);
    LoadBlockHashesCache(mnodeman);
    CMasternodeDB mndb;
    CMasternodeDB::ReadResult readResult = mndb.Read(mnodeman);
    if (readResult == CMasternodeDB::FileError)
        LogPrintf("Missing masternode cache file - mncache.dat, will try to recreate\n");
    else if (readResult != CMasternodeDB::Ok) {
        LogPrintf("Error reading mncache.dat - cached data discarded\n");
    }

    // ##################### //
    // ## Budget Manager ### //
    // ##################### //
    uiInterface.InitMessage(_("Loading budget cache..."));

    CBudgetDB budgetdb;
    const bool fDryRun = (chain_active_height <= 0);
    if (!fDryRun) g_budgetman.SetBestHeight(chain_active_height);
    CBudgetDB::ReadResult readResult2 = budgetdb.Read(g_budgetman, fDryRun);

    if (readResult2 == CBudgetDB::FileError)
        LogPrintf("Missing budget cache - budget.dat, will try to recreate\n");
    else if (readResult2 != CBudgetDB::Ok) {
        LogPrintf("Error reading budget.dat - cached data discarded\n");
    }

    // flag our cached items so we send them to our peers
    g_budgetman.ResetSync();
    g_budgetman.ReloadMapSeen();

    // ######################################### //
    // ## Legacy Masternodes-Payments Manager ## //
    // ######################################### //
    uiInterface.InitMessage(_("Loading masternode payment cache..."));

    CMasternodePaymentDB mnpayments;
    CMasternodePaymentDB::ReadResult readResult3 = mnpayments.Read(masternodePayments);
    if (readResult3 == CMasternodePaymentDB::FileError)
        LogPrintf("Missing masternode payment cache - mnpayments.dat, will try to recreate\n");
    else if (readResult3 != CMasternodePaymentDB::Ok) {
        LogPrintf("Error reading mnpayments.dat - cached data discarded\n");
    }

    return true;
}

void RegisterTierTwoValidationInterface()
{
    RegisterValidationInterface(&g_budgetman);
    RegisterValidationInterface(&masternodePayments);
}