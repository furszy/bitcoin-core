// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include "tiertwo/init.h"

#include "budget/budgetdb.h"
#include "flatdb.h"
#include "guiinterface.h"
#include "guiinterfaceutil.h"
#include "masternodeman.h"
#include "masternode-payments.h"
#include "masternodeconfig.h"
#include "tiertwo/masternode_meta_manager.h"
#include "validation.h"

#include <boost/thread.hpp>

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

bool LoadTierTwo(int chain_active_height, bool fReindexChainState)
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

    // init mn metadata manager
    bool fLoadCacheFiles = !(fReindex || fReindexChainState);
    fs::path pathDB = GetDataDir();
    std::string strDBName = "mnmetacache.dat";
    uiInterface.InitMessage(_("Loading masternode cache..."));
    CFlatDB<CMasternodeMetaMan> metadb(strDBName, "magicMasternodeMetaCache");
    if (fLoadCacheFiles) {
        if (!metadb.Load(g_mmetaman)) {
            return UIError(_("Failed to load masternode metadata cache from") + "\n" + (pathDB / strDBName).string());
        }
    } else {
        CMasternodeMetaMan mmetamanTmp;
        if (!metadb.Dump(mmetamanTmp)) {
            return UIError(_("Failed to clear masternode metadata cache at") + "\n" + (pathDB / strDBName).string());
        }
    }

    return true;
}

void RegisterTierTwoValidationInterface()
{
    RegisterValidationInterface(&g_budgetman);
    RegisterValidationInterface(&masternodePayments);
    if (activeMasternodeManager) RegisterValidationInterface(activeMasternodeManager);
}

void DumpTierTwo()
{
    DumpMasternodes();
    DumpBudgets(g_budgetman);
    DumpMasternodePayments();
    CFlatDB<CMasternodeMetaMan>("mnmetacache.dat", "magicMasternodeMetaCache").Dump(g_mmetaman);
}

void SetBudgetFinMode(const std::string& mode)
{
    g_budgetman.strBudgetMode = mode;
    LogPrintf("Budget Mode %s\n", g_budgetman.strBudgetMode);
}

bool InitActiveMN()
{
    fMasterNode = gArgs.GetBoolArg("-masternode", DEFAULT_MASTERNODE);
    if ((fMasterNode || masternodeConfig.getCount() > -1) && fTxIndex == false) {
        return UIError(strprintf(_("Enabling Masternode support requires turning on transaction indexing."
                                   "Please add %s to your configuration and start with %s"), "txindex=1", "-reindex"));
    }

    if (fMasterNode) {
        const std::string& mnoperatorkeyStr = gArgs.GetArg("-mnoperatorprivatekey", "");
        const bool fDeterministic = !mnoperatorkeyStr.empty();
        LogPrintf("IS %s MASTERNODE\n", (fDeterministic ? "DETERMINISTIC " : ""));

        if (fDeterministic) {
            // Check enforcement
            if (!deterministicMNManager->IsDIP3Enforced()) {
                const std::string strError = strprintf(
                        _("Cannot start deterministic masternode before enforcement. Remove %s to start as legacy masternode"),
                        "-mnoperatorprivatekey");
                LogPrintf("-- ERROR: %s\n", strError);
                return UIError(strError);
            }
            // Create and register activeMasternodeManager
            activeMasternodeManager = new CActiveDeterministicMasternodeManager();
            auto res = activeMasternodeManager->SetOperatorKey(mnoperatorkeyStr);
            if (!res) { return UIError(res.getError()); }
            // Init active masternode
            const CBlockIndex* pindexTip = WITH_LOCK(cs_main, return chainActive.Tip(););
            activeMasternodeManager->Init(pindexTip);
        } else {
            // Check enforcement
            if (deterministicMNManager->LegacyMNObsolete()) {
                const std::string strError = strprintf(
                        _("Legacy masternode system disabled. Use %s to start as deterministic masternode"),
                        "-mnoperatorprivatekey");
                LogPrintf("-- ERROR: %s\n", strError);
                return UIError(strError);
            }
            auto res = initMasternode(gArgs.GetArg("-masternodeprivkey", ""), gArgs.GetArg("-masternodeaddr", ""),
                                      true);
            if (!res) { return UIError(res.getError()); }
        }
    }
    // All good
    return true;
}

void StartTierTwoThreadsAndScheduleJobs(boost::thread_group& threadGroup, CScheduler& scheduler)
{
    threadGroup.create_thread(std::bind(&ThreadCheckMasternodes));
}
